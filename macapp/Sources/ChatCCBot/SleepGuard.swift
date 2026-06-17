import Foundation
import IOKit.pwr_mgt

// 防 Mac 空闲休眠：持一个 IOKit 电源断言。
// PreventUserIdleSystemSleep 只挡"空闲系统休眠"，不强开屏幕、最省电；app 退出自动释放。
// 注意：笔记本合盖的硬件休眠挡不住（物理限制）。
final class SleepGuard {
    private var id: IOPMAssertionID = 0
    private(set) var active = false

    func enable() {
        guard !active else { return }
        var aid: IOPMAssertionID = 0
        let r = IOPMAssertionCreateWithName(
            "PreventUserIdleSystemSleep" as CFString,
            IOPMAssertionLevel(kIOPMAssertionLevelOn),
            "DK 保持 Mac 唤醒，让 bot 在线" as CFString,
            &aid
        )
        if r == kIOReturnSuccess {
            id = aid
            active = true
        }
    }

    func disable() {
        guard active else { return }
        IOPMAssertionRelease(id)
        active = false
    }
}
