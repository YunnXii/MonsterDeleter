# 叫家琦来：文件清理小剧场

这是从 `MonsterDeleter` 改造而来的 Windows 文件清理工具。现在它已经是一个常驻桌面的 Q 版家琦：平时待在桌面角落，收到任务后走到目标旁边确认，再一脚把倒霉文件踹进回收站。

核心删除动画已经封版，当前开发重点是常驻桌面宠物、真实文件定位、真准星、托盘、多显示器和单 EXE 日用体验。

## 当前使用方式

直接运行：

```powershell
python main.py
```

或双击打包后的 `叫家琦来.exe`。

程序会自动安装 / 修复当前用户的文件和文件夹右键菜单，并常驻后台。桌面会出现一个小号 Q 版家琦，同时注册系统托盘作为兜底入口。

### 模式一：文件右键 —— 已完成

1. 在桌面或 Explorer 中右键一个文件 / 文件夹；
2. 选择“叫家琦来收拾它”；
3. 新启动的进程把完整 Path 通过本地 IPC 发给常驻实例后立即退出；
4. 常驻实例在后台通过 Windows UI Automation 查找这个 Path 对应的可见文件项；
5. 找到后直接取得文件图标的真实屏幕矩形，不再出现旧准星；
6. 小号 Pet 隐藏，正常尺寸家琦从 Pet 所在位置出发；
7. 走到目标附近问“就是「xxx」？”；
8. 确认后执行已经封版的踢飞动画和回收站逻辑。

同一屏幕时，正常尺寸角色从常驻小人的脚底位置直接出发；如果 Pet 与目标位于不同显示器，则从目标屏幕距离 Pet 更近的一侧进入，避免用侧身走路精灵跨屏斜穿造成奇怪观感。

定位时不会只凭文件名随便猜：

- 同时匹配完整文件名和隐藏扩展名时 Explorer 可能暴露的名称；
- 优先采用右键操作后仍保持 `Selected` 状态的 ListItem；
- 结合前台 Explorer 窗口、桌面 / 普通 Explorer 场景进行评分；
- 多个同名项仍无法确认时直接拒绝猜测。

如果文件所在的桌面或 Explorer 窗口没有露出来，会提示：

```text
我知道要踹谁，但没看见它站哪儿。
把文件所在的桌面或文件夹窗口露出来，再叫我一次。
```

如果同名项目过多且无法确认，会提示用户把目标窗口放到前面再试。不会退回旧的“随便点个坐标”模式。

### 模式二：右键常驻小人 → 瞄一个倒霉文件 —— 下一阶段

这一项目前仍刻意保持占位，不调用旧假准星。

下一阶段会实现：

```text
屏幕坐标
→ UI Automation / Shell 命中测试
→ 真实文件 Path + 文件矩形
→ 家琦直接走过去确认
```

完成以后，两种入口最终都会统一成同一种内部任务：`真实 Path + 真实屏幕位置`。

## 常驻小人

当前支持：

- 左键点击：随机趣味台词；
- 连续猛点：额外吐槽；
- 左键按住拖动：自由移动；
- 使用 `QSettings` 记住位置；
- 显示器变化导致位置失效时自动回主屏右下角；
- 右键打开功能菜单；
- 系统托盘兜底；
- 当前用户级开机启动。

右键菜单：

```text
瞄一个倒霉文件
──────────────
回到右下角
开机启动
──────────────
隐藏家琦 / 显示家琦
退出
```

Pet 点击互动通过 `InteractionProvider` 抽象。当前使用 `RandomQuipProvider`，未来可替换为 AI 对话 Provider，而不需要重写拖动、托盘、IPC 或删除逻辑。

## 单实例与 IPC

程序采用单实例常驻架构。已有实例运行时，再启动 EXE 不会生成第二只家琦。

右键菜单启动的新进程只负责：

```text
收到文件 Path
→ 连接 QLocalServer
→ 发送 Path
→ 退出
```

任务执行或目标解析期间暂不排队，新的请求会提示：

```text
手上正踹着一个呢，等等。
```

## 删除动画与失败处理

动画导演已封版：

```text
起步：1 → 2 → 3
巡航：3 → 6 → 4 → 2 → 循环
停车：提前预约第 3 帧合法停车相位
收步：6 → 7 → 8 → 9
等待：第 9 帧正面 + 1px 呼吸，停在攻击位外侧 40px
确认：9 → 8 → 7，同时前移 40px
攻击：转身完成 + 前移完成 → Kick
命中：Kick 5 → 后台回收站任务
成功：爆炸 + 图标抛飞 → 扶眼镜 → 微笑 → 冷脸
失败：自然收腿 → 正面提示 → 重试 / 快速溜走
```

关键参数：

- 行走速度约 `390 px/s`；
- 巡航 `105 / 85 / 105 / 85ms`；
- Kick 锚点 `impact_x=234 / impact_y=136`；
- 等待位额外外移 `40px`；
- Kick 第 5 帧是唯一命中帧。

删除运行在后台 `QRunnable`，Office / Shell 返回文件占用错误时不会冻结飞踢动画。

文件占用提示：

```text
这玩意正开着呢，踹不动。

[关了再踹一次]  [不踹了]
```

成功台词：

```text
这倒霉文件已经踹飞了。
```

## DPI 与多屏

UI Automation 的 `BoundingRectangle` 使用 Windows 物理像素，而 Qt 在高 DPI 下使用逻辑坐标。`target_resolver.py` 会根据目标所在显示器的物理边界和 `QScreen.devicePixelRatio()` 将命中位置转换成 Qt 全局逻辑坐标，再交给动画舞台。

目标继续覆盖：

- 主屏 / 副屏；
- 副屏位于主屏左侧或右侧；
- 100% / 150% / 200% Windows 缩放。

这部分仍需要真实 Windows 多屏组合继续验收。

## 开发入口

动画演示：

```powershell
python main.py --demo
```

Kick 命中校准：

```powershell
python main.py --calibrate-kick
```

这两个入口保持独立，不接入常驻单实例。

## 依赖与打包

```powershell
pip install -r requirements-dev.txt
python -m pytest -q
```

真实文件定位使用 `uiautomation`。构建脚本会通过 PyInstaller `--collect-all uiautomation` 将相关运行时一起收进单文件 EXE。

打包：

```powershell
pip install -r requirements.txt
.\build.ps1
```

输出：

```text
dist\叫家琦来.exe
```

CI 在 Windows 上实际执行测试与 onefile 构建，避免只在源码模式工作。

## 主要结构

```text
app/
  autostart.py           Windows 开机启动
  character.py           角色参数与锚点配置
  chibi_avatar.py        精灵播放器与动作状态机
  context_menu.py        文件 / 文件夹右键菜单
  delete_service.py      回收站、错误分类与 Shell 刷新
  delete_task.py         后台删除 QRunnable
  direct_overlay.py      已知真实目标坐标的无准星任务 Overlay
  interactions.py        Pet 互动 Provider
  pet_widget.py          常驻小人、拖动与气泡
  resident_controller.py 常驻生命周期、托盘、目标解析与任务 session
  responsive_overlay.py  非阻塞删除动画 Overlay
  single_instance.py     QLocalServer / QLocalSocket IPC
  target_resolver.py     Path → Desktop / Explorer 可见文件矩形
  overlay.py             基础舞台与封版动画流程
characters/jiaqi/
  character.json
  sprites/
    walk.png
    kick.png
    victory.png
```

当前不计划加入音效。下一步是把“瞄一个倒霉文件”做成真正能识别屏幕下方文件的准星。
