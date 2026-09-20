// OCR one or more images with Apple's Vision framework.
// Usage: swift tools/ocr.swift page1.png page2.png > text.jsonl
// Prints one JSON object per recognised line: {"file","text","x","y","w","h"}
import Foundation
import Vision
import AppKit

func escape(_ s: String) -> String {
    var out = ""
    for ch in s.unicodeScalars {
        switch ch {
        case "\"": out += "\\\""
        case "\\": out += "\\\\"
        case "\n", "\r", "\t": out += " "
        default: out.unicodeScalars.append(ch)
        }
    }
    return out
}

for path in CommandLine.arguments.dropFirst() {
    guard let image = NSImage(contentsOfFile: path),
          let cg = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
        FileHandle.standardError.write("cannot read \(path)\n".data(using: .utf8)!)
        continue
    }
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = false
    request.recognitionLanguages = ["ar-SA", "en-US"]
    let handler = VNImageRequestHandler(cgImage: cg, options: [:])
    do {
        try handler.perform([request])
    } catch {
        FileHandle.standardError.write("failed \(path): \(error)\n".data(using: .utf8)!)
        continue
    }
    let name = (path as NSString).lastPathComponent
    for observation in (request.results ?? []) {
        guard let best = observation.topCandidates(1).first else { continue }
        let b = observation.boundingBox
        print("{\"file\":\"\(escape(name))\",\"text\":\"\(escape(best.string))\"," +
              "\"x\":\(b.origin.x),\"y\":\(b.origin.y),\"w\":\(b.size.width),\"h\":\(b.size.height)}")
    }
}
