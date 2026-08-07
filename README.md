# 叫家琦来：文件清理小剧场

这是从 `MonsterDeleter` 改造而来的 Windows 文件清理工具。现在它已经是一个常驻桌面的 Q 版家琦：平时待在桌面角落，收到任务后走到目标旁边确认，再一脚把倒霉文件踹进回收站。

核心删除动画已经封版；常驻桌面宠物、文件右键无准星直达、真准星、托盘、多显示器基础适配和单 EXE 构建链均已接通。

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
6. 常驻 Pet 以脚底为固定锚点，在约 `210ms` 内从小号平滑放大到执行尺寸；
7. 正常尺寸家琦从同一个脚底位置出发，走到目标附近问“就是「xxx」？”；
8. 确认后执行已经封版的踢飞动画和回收站逻辑；
9. 成功或“不是不是”时快步回到原来的 Pet 停靠点，再用约 `180ms` 缩回小号待机状态。

同一屏幕时，正常尺寸角色从常驻小人的脚底位置直接出发，并在任务结束后真正走回原位。Pet 拖到哪里，哪里就是当前 Home。

如果 Pet 与目标位于不同显示器，出发阶段从目标屏幕距离 Pet 更近的一侧进入；回程时先走出当前屏幕，再把舞台切到 Home 所在屏幕，从靠近来源屏的一侧出现并继续走回停靠点。

定位时不会只凭文件名随便猜：

- 同时匹配完整文件名和隐藏扩展名时 Explorer 可能暴露的名称；
- 优先采用右键操作后仍保持 `Selected` 状态的 ListItem；
- 结合前台 Explorer 窗口、桌面 / 普通 Explorer 场景进行评分；
- 多个同名项仍无法确认时直接拒绝猜测。

Windows 桌面目录通过 `SHGetKnownFolderPath(FOLDERID_Desktop / FOLDERID_PublicDesktop)` 读取，支持把桌面迁移到 D 盘、OneDrive Known Folder Move 和企业文件夹重定向；Known Folder 异常时才回退注册表与传统 `~/Desktop`。

如果文件所在的桌面或 Explorer 窗口没有露出来，会提示：

```text
我知道要踹谁，但没看见它站哪儿。
把文件所在的桌面或文件夹窗口露出来，再叫我一次。
```

不会退回旧的“随便点个坐标”模式。

### 模式二：右键常驻小人 → 瞄一个倒霉文件 —— 已完成

1. 右键常驻小人，选择“瞄一个倒霉文件”；
2. 出现鼠标穿透的真准星；
3. Explorer 继续通过 UI Automation + Shell 解析；Windows 桌面则优先使用原生 `SysListView32 / FolderView` 的 `LVM_HITTEST`，不依赖桌面是否处于 UIA 活跃状态；
4. 左键点击由临时 Windows 低级鼠标 Hook 截获，不会真的打开文件；
5. 桌面通过原生 item index 读取显示名与图标矩形，再结合 Windows Known Folder 解析真实 Path；Explorer 则通过 `Shell.Application` 取得真实目录并处理隐藏扩展名；
6. 得到 `真实 Path + 真实屏幕矩形` 后关闭准星，直接复用模式一的执行流程；
7. 右键或 Esc 可取消瞄准；右键按下与抬起会完整吞掉，取消后不会顺手弹出 Desktop / Explorer 右键菜单。

桌面内部链路：

```text
屏幕物理坐标
→ Progman / WorkerW
→ SHELLDLL_DefView
→ SysListView32 / FolderView
→ LVM_HITTEST
→ item index
→ LVM_GETITEMTEXTW + LVM_GETITEMRECT
→ Known Folder Desktop
→ 真实 Path + 原生图标矩形
→ Qt 逻辑坐标
→ 常驻任务执行器
```

Explorer 内部链路：

```text
屏幕物理坐标
→ UI Automation ControlFromPoint
→ Explorer ListItem
→ Shell.Application 取得 Explorer 当前真实目录
→ 处理隐藏扩展名
→ 真实 Path + UIA BoundingRectangle
→ Qt 逻辑坐标
→ 常驻任务执行器
```

真准星不会只凭显示名冒险：如果隐藏扩展名导致例如 `资料` 文件夹与 `资料.docx` 在屏幕上都显示为“资料”，会直接判定歧义并拒绝乱踹。

点击空白处、非文件元素或无法解析成普通文件系统 Path 的虚拟位置时，准星会给出提示并继续留在瞄准状态，不会退出或随便选一个目标。

准星视觉层使用 `WindowTransparentForInput`，输入由瞄准期间临时存在的 `WH_MOUSE_LL / WH_KEYBOARD_LL` Hook 负责，因此透明层不会挡住底下 Explorer 或桌面的命中测试。

Hover 保留约 `320ms` 的视觉抗抖，但最终左键选择一定重新执行严格命中；Hover 缓存不会参与删除目标判断。

开发诊断可通过：

```powershell
$env:JIAQI_AIM_DEBUG="1"
python main.py
```

开启，原生桌面命中日志写入 `%LOCALAPPDATA%\JiaqiCleaner\aim-debug.log`。

两种入口现在最终都统一成同一种内部任务：`真实 Path + 真实屏幕位置`。

## 常驻小人

当前支持：

- 左键点击：随机趣味台词；
- 连续猛点：额外吐槽；
- 左键按住拖动：自由移动；
- 使用 `QSettings` 记住位置；
- 显示器变化导致位置失效时自动回主屏右下角；
- 右键打开功能菜单；
- 系统托盘兜底；
- 当前用户级开机启动；
- Pet ↔ 执行尺寸使用脚底锚定的平滑 morph，不再瞬间变大 / 变小；
- 成功任务与确认取消会回 Home；
- 删除失败后点“不踹了”仍保留高速逃跑喜剧退场，随后直接恢复 Home 处的小号 Pet。

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

任务执行、尺寸 morph、目标解析或真准星瞄准期间暂不排队，新的请求会提示：

```text
手上正踹着一个呢，等等。
```

## 删除动画与失败处理

动画导演已封版：

```text
Pet 出发：145px → 298px，约 210ms，脚底位置不变
起步：1 → 2 → 3
巡航：3 → 6 → 4 → 2 → 循环
停车：提前预约第 3 帧合法停车相位
收步：6 → 7 → 8 → 9
等待：第 9 帧正面 + 1px 呼吸，停在攻击位外侧 40px
确认：9 → 8 → 7，同时前移 40px
攻击：转身完成 + 前移完成 → Kick
命中：Kick 5 → 后台回收站任务
成功：爆炸 + 图标沿真实踢击方向抛飞 → 扶眼镜 → 微笑 → 冷脸
回程：约 640 px/s 快步返回 Home
到家：298px → 145px，约 180ms，脚底位置不变
失败：自然收腿 → 正面提示 → 重试 / 快速溜走
```

关键参数：

- 去程与回 Home 统一约 `640 px/s`；
- 巡航 `105 / 85 / 105 / 85ms`；
- Kick 锚点 `impact_x=234 / impact_y=136`；
- 等待位额外外移 `40px`；
- Kick 第 5 帧是唯一命中帧；
- 文件抛飞方向只看 Kick 命中时“人物 → 目标”的真实相对位置，不再用屏幕左右半区推断。

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

UI Automation 和原生桌面 ListView 都提供 Windows 物理像素，而 Qt 在高 DPI 下使用逻辑坐标。`target_resolver.py` 会根据目标所在显示器的物理边界和 `QScreen.devicePixelRatio()` 将命中位置转换成 Qt 全局逻辑坐标，再交给动画舞台。

目标继续覆盖：

- 主屏 / 副屏；
- 副屏位于主屏左侧或右侧；
- 100% / 150% / 200% Windows 缩放。

真准星的低级鼠标 Hook 直接取得 Windows 物理屏幕坐标，因此点击命中不经过 Qt 坐标反推；最终目标矩形仍通过统一转换交给动画层。

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

真实文件定位 / Explorer 真准星使用 `uiautomation`；Explorer 真实目录解析使用 `pywin32` 的 `Shell.Application`。桌面真准星优先使用 Win32 原生 `SysListView32` 消息，不新增额外依赖。构建脚本显式收集 `uiautomation`，并加入 `win32com.client / pythoncom / pywintypes` hidden imports。

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
  aim_input.py           真准星期间的临时鼠标 / Esc 低级 Hook
  aim_overlay.py         鼠标穿透准星与实时识别标签
  aim_resolver.py        屏幕点 → Desktop Native / Explorer UIA → 真实文件 Path
  native_desktop.py      Win32 Desktop ListView 原生命中与跨进程只读信息获取
  desktop_paths.py       Windows Known Folder 桌面路径解析
  autostart.py           Windows 开机启动
  character.py           角色参数与锚点配置
  chibi_avatar.py        精灵播放器与动作状态机
  context_menu.py        文件 / 文件夹右键菜单
  delete_service.py      回收站、错误分类与 Shell 刷新
  delete_task.py         后台删除 QRunnable
  direct_overlay.py      已知真实目标坐标的无准星任务 Overlay
  interactions.py        Pet 互动 Provider
  pet_widget.py          常驻小人、拖动、气泡与视觉锚点
  resident_controller.py 常驻生命周期、托盘、真准星、回 Home 与任务 session
  resident_transition.py Pet ↔ 执行尺寸的脚底锚定 morph
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

当前不计划加入音效。下一阶段以 Windows 实机多屏 / DPI 和最终交付体验验收为主，再决定是否进入安装包、自动更新或 AI 互动等扩展。
