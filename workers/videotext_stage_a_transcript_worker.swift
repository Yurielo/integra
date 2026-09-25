import Foundation

private struct StageARequest: Decodable {
    let schemaVersion: String
    let sourceMediaPath: String
    let projectPath: String
    let whisperModelPath: String
    let language: String

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case sourceMediaPath = "source_media_path"
        case projectPath = "project_path"
        case whisperModelPath = "whisper_model_path"
        case language
    }
}

@main
struct IntegraVideoTextStageATranscriptWorker {
    static func main() async {
        do {
            guard CommandLine.arguments.count == 3,
                  CommandLine.arguments[1] == "--stage-a-request" else {
                throw StageAWorkerError.failed("usage: worker --stage-a-request <request.json>")
            }
            let requestURL = URL(fileURLWithPath: CommandLine.arguments[2])
            let request = try JSONDecoder().decode(StageARequest.self, from: Data(contentsOf: requestURL))
            guard request.schemaVersion == "1.0", request.language == "ru" else {
                throw StageAWorkerError.failed("unsupported Stage A request")
            }
            let mediaURL = URL(fileURLWithPath: request.sourceMediaPath)
            let projectURL = URL(fileURLWithPath: request.projectPath)
            let modelURL = URL(fileURLWithPath: request.whisperModelPath)
            guard mediaURL.path.hasPrefix("/"), projectURL.path.hasPrefix("/"), modelURL.path.hasPrefix("/") else {
                throw StageAWorkerError.failed("Stage A paths must be absolute")
            }
            let settings = WorkflowSettings(
                mediaURL: mediaURL,
                projectURL: projectURL,
                selectedOperations: [.assessTranscriptionQuality],
                mode: .newProject,
                rangeStart: 0,
                rangeEnd: 1,
                fragmentName: "",
                burnFragmentSubtitles: false,
                subtitleStyle: .standard,
                selectedTopicID: nil,
                whisperModelPath: modelURL.path,
                whisperLanguage: request.language,
                sourceHumanReviewEnabled: true,
                translationHumanReviewEnabled: false,
                fillerAnalysisBeforeReview: false,
                topicHumanReviewEnabled: false
            )
            let result = try await WorkflowEngine().run(settings: settings, onLog: { print("VIDEOTEXT_LOG \($0)") })
            guard let checkpoint = result.checkpoint, checkpoint.kind == .sourceTranscript else {
                throw StageAWorkerError.failed("source transcript review checkpoint missing")
            }
            let layout = ProjectLayout(root: result.projectURL)
            let required = [layout.fullSRTURL, layout.transcriptURL, layout.whisperJSONURL, layout.manifestURL,
                            layout.transcriptionQualityURL, layout.reviewTasksURL]
            for url in required where !FileManager.default.fileExists(atPath: url.path) {
                throw StageAWorkerError.failed("expected output missing: \(url.lastPathComponent)")
            }
            let report: [String: Any] = [
                "schema_version": "1.0",
                "component": "videotext",
                "capability": "stage_a_transcript",
                "project_path": result.projectURL.path,
                "srt_path": layout.fullSRTURL.path,
                "transcript_path": layout.transcriptURL.path,
                "whisper_json_path": layout.whisperJSONURL.path,
                "manifest_path": layout.manifestURL.path,
                "quality_path": layout.transcriptionQualityURL.path,
                "review_tasks_path": layout.reviewTasksURL.path,
                "review_checkpoint": "SOURCE_TRANSCRIPT",
                "semantic_authority": "MACHINE_UNVERIFIED"
            ]
            let data = try JSONSerialization.data(withJSONObject: report, options: [.sortedKeys])
            print("INTEGRA_VIDEOTEXT_STAGE_A_RESULT " + String(decoding: data, as: UTF8.self))
        } catch {
            fputs("INTEGRA_VIDEOTEXT_STAGE_A_ERROR \(error.localizedDescription)\n", stderr)
            exit(1)
        }
    }
}

private enum StageAWorkerError: LocalizedError {
    case failed(String)
    var errorDescription: String? { switch self { case .failed(let message): return message } }
}
