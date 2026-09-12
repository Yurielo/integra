import Foundation

@main
struct IntegraVideoTextTranslationWorker {
    static func main() async {
        do {
            let arguments = Array(CommandLine.arguments.dropFirst())
            guard let input = value("--srt", in: arguments), let output = value("--output", in: arguments),
                  let targetValue = value("--target", in: arguments),
                  let target = ArtifactLanguage(rawValue: targetValue) else {
                throw WorkerError.invalidArguments
            }
            let sourceURL = URL(fileURLWithPath: input)
            let source = try String(contentsOf: sourceURL, encoding: .utf8)
            let cues = try parseSRT(source)
            let original = source.contains(where: { $0.unicodeScalars.contains { (0x0400...0x04FF).contains($0.value) } }) ? ArtifactLanguage.ru : .en
            let result = try await TranslationAdapter().translate(cues: cues, source: original, target: target, onProgress: { _ in }, onLog: { _ in })
            let translated = result.cues.map { ["id": $0.id, "start_seconds": $0.start, "end_seconds": $0.end, "text": $0.text] as [String: Any] }
            let issues = result.issues.map { ["cue_id": $0.cueID, "reason_codes": $0.reasonCodes, "candidate_text": $0.candidateText as Any] as [String: Any] }
            let payload: [String: Any] = ["schema_version": "1.0", "component": "videotext", "capability": "translation", "source_language": original.rawValue, "target_language": target.rawValue, "model": result.model, "semantic_status": "MACHINE_TRANSLATION_REVIEW_REQUIRED", "cues": translated, "issues": issues]
            let data = try JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys, .prettyPrinted])
            try data.write(to: URL(fileURLWithPath: output), options: .atomic)
        } catch {
            fputs("VideoText translation failed: \(error.localizedDescription)\n", stderr)
            exit(2)
        }
    }

    static func value(_ name: String, in arguments: [String]) -> String? {
        guard let index = arguments.firstIndex(of: name), arguments.indices.contains(index + 1) else { return nil }
        return arguments[index + 1]
    }

    static func parseSRT(_ text: String) throws -> [SubtitleCue] {
        let blocks = text.components(separatedBy: "\n\n").filter { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
        let cues = try blocks.map { block -> SubtitleCue in
            let lines = block.components(separatedBy: .newlines)
            guard lines.count >= 3, let id = Int(lines[0]), lines[1].contains(" --> ") else { throw WorkerError.invalidSRT }
            let bounds = lines[1].components(separatedBy: " --> ")
            guard bounds.count == 2 else { throw WorkerError.invalidSRT }
            return SubtitleCue(id: id, start: try seconds(bounds[0]), end: try seconds(bounds[1]), text: lines.dropFirst(2).joined(separator: " "))
        }
        guard !cues.isEmpty else { throw WorkerError.invalidSRT }
        return cues
    }

    static func seconds(_ value: String) throws -> TimeInterval {
        let units = value.replacingOccurrences(of: ",", with: ".").split(separator: ":")
        guard units.count == 3, let hours = Double(units[0]), let minutes = Double(units[1]), let seconds = Double(units[2]) else { throw WorkerError.invalidSRT }
        return hours * 3600 + minutes * 60 + seconds
    }
}

enum WorkerError: LocalizedError { case invalidArguments, invalidSRT }
