import Foundation

/// Transport only: all media processing belongs to the pinned VideoText services.
enum IntegraVideoTextMediaWorker {
    struct Request: Decodable {
        let schema_version: String
        let operation: String
        let input_media: String
        let output_path: String
        let input_srt: String?
        let start_seconds: Double?
        let end_seconds: Double?
        let speed_factor: Double?
    }

    static func run(requestPath: String) async throws {
        let data = try Data(contentsOf: URL(fileURLWithPath: requestPath))
        let allowed: Set<String> = ["schema_version", "operation", "input_media", "output_path", "input_srt", "start_seconds", "end_seconds", "speed_factor"]
        guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any], Set(object.keys).isSubset(of: allowed) else { throw WorkerError.invalidArguments }
        let request = try JSONDecoder().decode(Request.self, from: data)
        guard request.schema_version == "1.0", ["clip", "burn_subtitles", "speed", "audio_analysis"].contains(request.operation) else { throw WorkerError.invalidArguments }
        let manager = FileManager.default
        func source(_ path: String) throws -> URL {
            let url = URL(fileURLWithPath: path).standardizedFileURL
            guard path.hasPrefix("/"), url.resolvingSymlinksInPath() == url,
                  (try url.resourceValues(forKeys: [.isRegularFileKey])).isRegularFile == true else { throw WorkerError.invalidArguments }
            return url
        }
        let input = try source(request.input_media)
        let output = URL(fileURLWithPath: request.output_path).standardizedFileURL
        guard request.output_path.hasPrefix("/"), output.resolvingSymlinksInPath() == output,
              !manager.fileExists(atPath: output.path),
              (try? manager.destinationOfSymbolicLink(atPath: output.path)) == nil,
              (try output.deletingLastPathComponent().resourceValues(forKeys: [.isDirectoryKey])).isDirectory == true else { throw WorkerError.invalidArguments }
        for value in [request.start_seconds, request.end_seconds, request.speed_factor].compactMap({ $0 }) {
            guard value.isFinite, value >= 0 else { throw WorkerError.invalidArguments }
        }
        let adapter = FFmpegAdapter()
        guard let duration = try await adapter.duration(of: input), duration.isFinite, duration > 0 else { throw WorkerError.invalidArguments }
        let temporary = output.deletingLastPathComponent().appendingPathComponent(".videotext-media-\(UUID().uuidString)", isDirectory: true)
        try manager.createDirectory(at: temporary, withIntermediateDirectories: false)
        defer { try? manager.removeItem(at: temporary) }
        let staged = temporary.appendingPathComponent(request.operation == "audio_analysis" ? "result.json" : "result.mp4")
        var expectedDuration = duration
        switch request.operation {
        case "clip":
            guard let start = request.start_seconds, let end = request.end_seconds, start < end, end <= duration + 0.01,
                  request.input_srt == nil, request.speed_factor == nil else { throw WorkerError.invalidArguments }
            expectedDuration = end - start
            try await adapter.cutAccurate(mediaURL: input, start: start, end: end, outputURL: staged, onProgress: { _ in })
        case "burn_subtitles":
            guard let path = request.input_srt, request.start_seconds == nil, request.end_seconds == nil, request.speed_factor == nil else { throw WorkerError.invalidArguments }
            let srt = try source(path)
            let service = SRTService()
            let report = try service.parseWithReport(String(contentsOf: srt, encoding: .utf8))
            guard report.skippedZeroDurationCount == 0, !report.cues.isEmpty,
                  report.cues.allSatisfy({ $0.start.isFinite && $0.end.isFinite && $0.start >= 0 && $0.end > $0.start }),
                  service.validateTimeline(report.cues, mediaDuration: duration).isEmpty else { throw WorkerError.invalidSRT }
            _ = try await adapter.burnSubtitles(mediaURL: input, srtURL: srt, outputURL: staged, mediaDuration: duration, copyAudio: false, onProgress: { _ in })
        case "speed":
            guard let factor = request.speed_factor, factor >= 0.5, factor <= 2,
                  request.input_srt == nil, request.start_seconds == nil, request.end_seconds == nil else { throw WorkerError.invalidArguments }
            expectedDuration = duration / factor
            _ = try await adapter.adjustSpeed(mediaURL: input, outputURL: staged, speedFactor: factor, mediaDuration: duration, onProgress: { _ in })
        case "audio_analysis":
            guard request.input_srt == nil, request.start_seconds == nil, request.end_seconds == nil, request.speed_factor == nil else { throw WorkerError.invalidArguments }
            let analysis = try await AudioEnhancementAdapter().analyze(mediaURL: input)
            let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys, .prettyPrinted]
            try encoder.encode(analysis).write(to: staged, options: .atomic)
        default: throw WorkerError.invalidArguments
        }
        var validation = "audio-analysis"
        var actualDuration = duration
        if request.operation != "audio_analysis" {
            validation = try await adapter.strictValidationReport(mediaURL: staged, expectedDuration: expectedDuration)
            guard let actual = try await adapter.duration(of: staged), actual.isFinite, actual > 0 else { throw WorkerError.invalidArguments }
            actualDuration = actual
        }
        guard (try staged.resourceValues(forKeys: [.fileSizeKey])).fileSize ?? 0 > 0 else { throw WorkerError.invalidArguments }
        try manager.linkItem(at: staged, to: output)
        let result: [String: Any] = ["schema_version": "1.0", "component": "videotext", "capability": "media", "operation": request.operation,
            "output_path": output.path, "source_duration_seconds": duration, "duration_seconds": actualDuration,
            "expected_duration_seconds": expectedDuration, "validation": validation]
        print(String(decoding: try JSONSerialization.data(withJSONObject: result, options: [.sortedKeys]), as: UTF8.self))
    }
}
