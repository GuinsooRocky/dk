import AppKit

// 离屏渲染 DK 图标 → 1024 PNG。用法：swift make_icon.swift <out.png>
let size: CGFloat = 1024
let rep = NSBitmapImageRep(
    bitmapDataPlanes: nil, pixelsWide: Int(size), pixelsHigh: Int(size),
    bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
    colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!

NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
let ctx = NSGraphicsContext.current!.cgContext

// 圆角矩形（macOS 风格 squircle 近似），留边
let margin = size * 0.085
let rect = CGRect(x: margin, y: margin, width: size - 2 * margin, height: size - 2 * margin)
let radius = rect.width * 0.225
let path = CGPath(roundedRect: rect, cornerWidth: radius, cornerHeight: radius, transform: nil)

// 紫色对角渐变
ctx.saveGState()
ctx.addPath(path)
ctx.clip()
let colors = [
    CGColor(red: 0.56, green: 0.41, blue: 1.00, alpha: 1),
    CGColor(red: 0.36, green: 0.29, blue: 0.92, alpha: 1),
] as CFArray
let grad = CGGradient(colorsSpace: CGColorSpaceCreateDeviceRGB(), colors: colors, locations: [0, 1])!
ctx.drawLinearGradient(grad, start: CGPoint(x: rect.minX, y: rect.maxY),
                       end: CGPoint(x: rect.maxX, y: rect.minY), options: [])
ctx.restoreGState()

// "DK" 白色加粗居中
let para = NSMutableParagraphStyle()
para.alignment = .center
let font = NSFont.systemFont(ofSize: size * 0.40, weight: .bold)
let attrs: [NSAttributedString.Key: Any] = [
    .font: font, .foregroundColor: NSColor.white, .paragraphStyle: para,
    .kern: -size * 0.01,
]
let str = NSAttributedString(string: "DK", attributes: attrs)
let ts = str.size()
str.draw(in: CGRect(x: 0, y: (size - ts.height) / 2, width: size, height: ts.height))

NSGraphicsContext.restoreGraphicsState()

let out = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "/tmp/dk_1024.png"
let png = rep.representation(using: .png, properties: [:])!
try! png.write(to: URL(fileURLWithPath: out))
print("wrote \(out)")
