import Foundation

@main
struct IntegraVideoTextTranscriptWorker {
    static func main() async {
        do {
            guard CommandLine.arguments.count == 3 else {
                throw WorkerError.failed("usage: worker <video> <whisper-model>")
            }
            let mediaURL = URL(fileURLWithPath: CommandLine.arguments[1])
            let settings = WorkflowSettings(
                mediaURL: mediaURL,
                projectURL: nil,
                selectedOperations: [.assessTranscriptionQuality],
                mode: .newProject,
                rangeStart: 0,
                rangeEnd: 1,
                fragmentName: "",
                burnFragmentSubtitles: false,
                subtitleStyle: .standard,
                selectedTopicID: nil,
                whisperModelPath: CommandLine.arguments[2],
                whisperLanguage: "ru",
                sourceHumanReviewEnabled: true,
                translationHumanReviewEnabled: false,
                fillerAnalysisBeforeReview: false,
                topicHumanReviewEnabled: true
            )
            let result = try await WorkflowEngine().run(
                settings: settings,
                onLog: { print("VIDEOTEXT_LOG \($0)") }
            )
            guard let checkpoint = result.checkpoint,
                  checkpoint.kind == .sourceTranscript else {
                throw WorkerError.failed("source transcript review checkpoint missing")
            }
            let layout = ProjectLayout(root: result.projectURL)
            for url in [layout.fullSRTURL, layout.transcriptURL, layout.whisperJSONURL, layout.manifestURL] {
                guard FileManager.default.fileExists(atPath: url.path) else {
                    throw WorkerError.failed("expected output missing: \(url.lastPathComponent)")
                }
            }
            let report: [String: Any] = [
                "schema_version": "1.0",
                "component": "videotext",
                "component_version": BuildInfo.version,
                "component_build": BuildInfo.build,
                "project_path": result.projectURL.path,
                "srt_path": layout.fullSRTURL.path,
                "transcript_path": layout.transcriptURL.path,
                "whisper_json_path": layout.whisperJSONURL.path,
                "manifest_path": layout.manifestURL.path,
                "review_checkpoint": "SOURCE_TRANSCRIPT",
                "semantic_authority": "MACHINE_UNVERIFIED"
            ]
            let data = try JSONSerialization.data(withJSONObject: report, options: [.sortedKeys])
            print("INTEGRA_VIDEOTEXT_TRANSCRIPT_RESULT " + String(decoding: data, as: UTF8.self))
        } catch {
            fputs("INTEGRA_VIDEOTEXT_TRANSCRIPT_ERROR \(error.localizedDescription)\n", stderr)
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
