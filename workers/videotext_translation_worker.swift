import Foundation

@main
struct IntegraVideoTextTranslationWorker {
    static func main() async {
        do {
            let arguments = Array(CommandLine.arguments.dropFirst())
            if arguments.count == 2, arguments[0] == "--media-request" {
                try await IntegraVideoTextMediaWorker.run(requestPath: arguments[1])
                return
            }
            if arguments.contains("--subtitle-request") {
                guard arguments.count == 2, arguments[0] == "--subtitle-request" else {
                    throw WorkerError.invalidArguments
                }
                try subtitles(requestPath: arguments[1])
                return
            }
            // Translation inference is Integra-owned and runs through the
            // TranslateGemma runtime. This worker remains intentionally
            // limited to VideoText-owned media and subtitle mechanics.
            throw WorkerError.invalidArguments
        } catch {
            // Component errors may contain private text or filesystem paths.
            fputs("VideoText worker failed: invalid request, subtitle data, or component operation.\n", stderr)
            exit(2)
        }
    }

    struct SubtitleRequest: Decodable {
        let schema_version: String
        let operation: String
        let input_srt: String
        let output_srt: String
        let media_duration: Double?
        let start_seconds: Double?
        let end_seconds: Double?
        let speed_factor: Double?
    }

    static func subtitles(requestPath: String) throws {
        let request = try JSONDecoder().decode(SubtitleRequest.self, from: Data(contentsOf: URL(fileURLWithPath: requestPath)))
        guard request.schema_version == "1.0", ["normalize", "clip", "speed"].contains(request.operation),
              request.input_srt.hasPrefix("/"), request.output_srt.hasPrefix("/") else {
            throw WorkerError.invalidArguments
        }
        let sourceURL = URL(fileURLWithPath: request.input_srt).standardizedFileURL
        let outputURL = URL(fileURLWithPath: request.output_srt).standardizedFileURL
        let manager = FileManager.default
        guard sourceURL.resolvingSymlinksInPath() != outputURL.resolvingSymlinksInPath(),
              !manager.fileExists(atPath: outputURL.path),
              (try? manager.destinationOfSymbolicLink(atPath: outputURL.path)) == nil else {
            throw WorkerError.invalidArguments
        }
        for number in [request.media_duration, request.start_seconds, request.end_seconds, request.speed_factor].compactMap({ $0 }) {
            guard number.isFinite, number >= 0 else { throw WorkerError.invalidArguments }
        }
        if let duration = request.media_duration, duration <= 0 { throw WorkerError.invalidArguments }
        let service = SRTService()
        let original = try String(contentsOf: sourceURL, encoding: .utf8)
        let input = request.operation == "normalize" ? numberedUpstreamSRT(original) : original
        let parsed = try service.parseWithReport(input)
        guard parsed.skippedZeroDurationCount == 0 else { throw WorkerError.invalidSRT }
        try validate(parsed.cues, service: service, duration: request.media_duration)
        let cues: [SubtitleCue]
        let outputDuration: Double?
        switch request.operation {
        case "normalize":
            guard request.start_seconds == nil, request.end_seconds == nil, request.speed_factor == nil else {
                throw WorkerError.invalidArguments
            }
            cues = parsed.cues
            outputDuration = request.media_duration
        case "clip":
            guard let start = request.start_seconds, let end = request.end_seconds, end > start,
                  request.speed_factor == nil else { throw WorkerError.invalidArguments }
            if let duration = request.media_duration, end > duration { throw WorkerError.invalidArguments }
            cues = service.cues(in: parsed.cues, start: start, end: end, rebased: true)
            outputDuration = end - start
        case "speed":
            guard let factor = request.speed_factor, request.start_seconds == nil, request.end_seconds == nil else {
                throw WorkerError.invalidArguments
            }
            cues = try service.cues(parsed.cues, adjustedForSpeed: factor)
            outputDuration = request.media_duration.map { $0 / factor }
        default:
            throw WorkerError.invalidArguments
        }
        try validate(cues, service: service, duration: outputDuration)
        // Write through the original component, verify its serialized timeline, then
        // promote exclusively. Never overwrite an existing user-owned destination.
        let staging = outputURL.deletingLastPathComponent().appendingPathComponent(".integra-srt-\(UUID().uuidString)", isDirectory: true)
        try manager.createDirectory(at: staging, withIntermediateDirectories: false)
        defer { try? manager.removeItem(at: staging) }
        let stagedOutput = staging.appendingPathComponent("subtitles.srt")
        try service.write(cues, to: stagedOutput)
        let written = try service.loadWithReport(from: stagedOutput)
        guard written.skippedZeroDurationCount == 0, written.cues.count == cues.count,
              zip(written.cues, cues).allSatisfy({
                  $0.0.text == $0.1.text && abs($0.0.start - $0.1.start) <= 0.000501 &&
                  abs($0.0.end - $0.1.end) <= 0.000501
              }) else { throw WorkerError.invalidSRT }
        try validate(written.cues, service: service, duration: outputDuration)
        let payload: [String: Any] = ["schema_version": "1.0", "component": "videotext", "capability": "subtitles",
            "operation": request.operation, "cue_count": written.cues.count, "output_srt": outputURL.path,
            "skipped_zero_duration_count": 0, "warnings": [String]()]
        let response = try JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
        try manager.linkItem(at: stagedOutput, to: outputURL)
        FileHandle.standardOutput.write(response)
        FileHandle.standardOutput.write(Data("\n".utf8))
    }

    static func validate(_ cues: [SubtitleCue], service: SRTService, duration: Double?) throws {
        // Guard the pinned writer's Double-to-Int millisecond conversion as well
        // as component timeline validation. No timestamp parsing is duplicated.
        guard cues.allSatisfy({ $0.start.isFinite && $0.end.isFinite && $0.start >= 0 &&
            $0.end > $0.start && $0.end < Double(Int32.max) * 3600 }),
              service.validateTimeline(cues, mediaDuration: duration).isEmpty else { throw WorkerError.invalidSRT }
    }

    static func numberedUpstreamSRT(_ text: String) -> String {
        // SeminarText emits unnumbered SRT. Add only block IDs; VideoText owns
        // all timestamp parsing, text handling, validation and serialization.
        let normalized = text.replacingOccurrences(of: "\r\n", with: "\n")
        return normalized.components(separatedBy: "\n\n").enumerated().map { index, block in
            if block.components(separatedBy: "\n").first?.contains(" --> ") == true {
                return "\(index + 1)\n\(block)"
            }
            return block
        }.joined(separator: "\n\n")
    }
}

enum WorkerError: LocalizedError { case invalidArguments, invalidSRT }
