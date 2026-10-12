// Image feature prints with Apple's Vision framework (on every Mac; nothing to download).
// The same idea as PseudoClient's CNN embeddings: a vector per image, so nearness can be measured.
//   swift featureprint.swift out.json image1.jpg image2.png ...
import Foundation
import Vision

let args = CommandLine.arguments
let out = URL(fileURLWithPath: args[1])
var result: [String: [Float]] = [:]
for path in args.dropFirst(2) {
    let handler = VNImageRequestHandler(url: URL(fileURLWithPath: path), options: [:])
    let request = VNGenerateImageFeaturePrintRequest()
    do {
        try handler.perform([request])
        guard let fp = request.results?.first as? VNFeaturePrintObservation else { continue }
        let n = fp.elementCount
        var v = [Float](repeating: 0, count: n)
        fp.data.withUnsafeBytes { raw in
            if fp.elementType == .float {
                let p = raw.bindMemory(to: Float.self); for i in 0..<n { v[i] = p[i] }
            } else {
                let p = raw.bindMemory(to: Double.self); for i in 0..<n { v[i] = Float(p[i]) }
            }
        }
        result[path] = v
    } catch {
        FileHandle.standardError.write("skipped \(path): \(error)\n".data(using: .utf8)!)
    }
}
let data = try JSONSerialization.data(withJSONObject: result)
try data.write(to: out)
print("\(result.count) feature prints")
