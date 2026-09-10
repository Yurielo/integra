import Foundation

@main
struct IntegraVideoTextClipWorker {
    static func main() async {
        do {
            guard CommandLine.arguments.count == 5,
                  let start = TimeInterval(CommandLine.arguments[2]),
                  let end = TimeInterval(CommandLine.arguments[3]) else {
                throw WorkerError.failed("usage: worker <video> <start> <end> <output>")
            }
            let source = URL(fileURLWithPath: CommandLine.arguments[1])
            let output = URL(fileURLWithPath: CommandLine.arguments[4])
            let adapter = FFmpegAdapter()
            try await adapter.cutAccurate(
                mediaURL: source,
                start: start,
                end: end,
                outputURL: output,
                onProgress: { _ in }
            )
            guard FileManager.default.fileExists(atPath: output.path),
                  let duration = try await adapter.duration(of: output),
                  duration > 0 else {
                throw WorkerError.failed("media clip was not created or validated")
            }
            let report: [String: Any] = [
                "schema_version": "1.0",
                "component": "videotext",
                "component_version": BuildInfo.version,
                "component_build": BuildInfo.build,
                "source_path": source.path,
                "output_path": output.path,
                "start_seconds": start,
                "end_seconds": end,
                "duration_seconds": duration
            ]
            let data = try JSONSerialization.data(withJSONObject: report, options: [.sortedKeys])
            print("INTEGRA_VIDEOTEXT_CLIP_RESULT " + String(decoding: data, as: UTF8.self))
        } catch {
            fputs("INTEGRA_VIDEOTEXT_CLIP_ERROR \(error.localizedDescription)\n", stderr)
            exit(1)
        }
    }
}

enum WorkerError: LocalizedError {
    case failed(String)
    var errorDescription: String? {
        switch self { case .failed(let message): return message }
    }
}
