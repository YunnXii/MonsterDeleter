# 叫家琦来：文件清理小剧场

这是从 `MonsterDeleter` 改造而来的 Windows 文件清理工具。现在它不再只是“一次性启动一个删除动画”，而是一个常驻桌面的 Q 版家琦：平时蹲在右下角，收到任务后再去收拾倒霉文件。

核心删除动画已经封版；当前开发重点转向常驻桌面宠物、真实文件定位、真准星、右键菜单、托盘、多显示器和单 EXE 日用体验。

## 首次运行与常驻

直接运行：

```powershell
python main.py
```

或双击打包后的 `叫家琦来.exe`。

程序会：

- 自动检查并安装当前用户的“叫家琦来收拾它”文件 / 文件夹右键菜单；
- 如果 EXE 或源码目录换了位置，自动修复注册表里的旧路径；
- 进入常驻模式，而不是直接播放全屏动画；
- 在桌面右下角显示一个小号 Q 版家琦；
- 同时注册系统托盘图标作为兜底入口。

右键菜单写在 `HKEY_CURRENT_USER`，不要求管理员权限。

也可以显式执行：

```powershell
python main.py --install-menu
python main.py --uninstall-menu
```

## 常驻小人

当前常驻小人已经支持：

- 左键点击：播放本地随机趣味台词；
- 连续猛点：进入另一组吐槽台词；
- 左键按住并拖动：自由移动位置；
- 拖动位置使用 `QSettings` 保存，下次启动继续待在原处；
- 显示器被拔掉或保存位置跑出所有屏幕时，自动回到主屏右下角；
- 右键：打开小人菜单；
- 系统托盘：即使小人被隐藏，也可以重新叫回来。

右键菜单目前包括：

```text
瞄一个倒霉文件
──────────────
回到右下角
开机启动
──────────────
隐藏家琦 / 显示家琦
退出
```

“开机启动”使用当前用户的 Windows Run 注册表项，不需要管理员权限。

### 趣味互动为未来 AI 留好了接口

Pet 本身不直接写死 `random.choice(...)`。点击只发出互动请求，台词由 `InteractionProvider` 提供。

当前使用：

```text
RandomQuipProvider
```

未来可以替换成：

```text
AIChatProvider
```

这样以后把左键点击升级为 AI 对话时，不需要推翻拖动、托盘、IPC 或删除动画。

## 单实例与右键菜单 IPC

程序现在是单实例常驻架构。

当后台已经有一只家琦时，再次双击 EXE只会唤醒已有实例，不会再生成第二只。

文件右键菜单仍然启动同一个 EXE，但新进程只负责：

```text
收到文件 Path
→ 连接本地 QLocalServer
→ 把 Path 发给常驻实例
→ 立即退出
```

主实例使用 `QLocalServer / QLocalSocket` 接收任务，不开放 TCP 端口，也不经过 Windows 防火墙。

任务执行期间如果又收到第二个目标，第一版不排队，会提示：

```text
手上正踹着一个呢，等等。
```

## 当前阶段：真实目标定位还没有伪装成“做完了”

常驻架构已经完成，但下面两项刻意留到下一阶段单独实现：

1. **已知 Path → 自动找到桌面 / Explorer 中这个文件的真实屏幕矩形**；
2. **真准星：屏幕坐标 → UI Automation / Shell 元素 → 真实文件 Path**。

因此当前分支中，文件右键任务虽然已经通过 IPC 交给常驻实例，进入现有 Cleaner session 后仍暂时需要旧的“点击目标位置”步骤。

右键小人的“瞄一个倒霉文件”也不会偷偷调用旧假准星；目前只提示真准星尚在接线。

下一阶段完成后，最终交互会变成：

```text
模式一：文件右键
文件 Path → 自动定位图标 → 不出现准星 → 家琦直接走过去确认

模式二：右键小人 → 瞄一个倒霉文件
真准星识别鼠标下面的实际文件 → 得到 Path + 屏幕矩形 → 家琦走过去确认
```

## 删除动画与失败处理

执行任务时仍然使用已经调好的动画状态机：

```text
起步：1 → 2 → 3
巡航：3 → 6 → 4 → 2 → 循环
停车：提前预约第 3 帧合法停车相位
收步：6 → 7 → 8 → 9
等待：第 9 帧正面 + 1px 呼吸，停在攻击位外侧 40px
确认：9 → 8 → 7，同时前移 40px
攻击：转身完成 + 前移完成 → Kick
命中：Kick 5 → 回收站任务
成功：爆炸 + 图标抛飞 → 扶眼镜 → 微笑 → 冷脸
```

关键参数：

- 行走速度约 `390 px/s`；
- 巡航 `105 / 85 / 105 / 85ms`；
- Kick 锚点 `impact_x=234 / impact_y=136`；
- 等待位额外外移 `40px`；
- Kick 第 5 帧是唯一命中帧。

删除操作运行在后台 `QRunnable` 中。Office / Windows Shell 即使花一两秒才返回“文件被占用”，也不会再把人物冻结在飞踢帧。

文件占用时显示：

```text
这玩意正开着呢，踹不动。

[关了再踹一次]  [不踹了]
```

“关了再踹一次”会原地重新转身开踹；“不踹了”会转向最近屏幕边缘快速溜走。

成功台词：

```text
这倒霉文件已经踹飞了。
```

## 图标抛飞

不会直接移动 Explorer 的真实桌面图标。程序会在删除前读取目标的系统图标，成功后生成一个透明图标替身：

- 水平初速度约 `1050 px/s`；
- 向上初速度约 `680 px/s`；
- 重力约 `1650 px/s²`；
- 自旋约 `720°/s`；
- 飞出舞台后自动销毁。

## 多屏与 DPI

当前 Cleaner session 会在用户选定目标位置后锁定到目标所在显示器，后续站位、踢击、对话框和离场使用该显示器自己的 Qt 逻辑坐标。

常驻 Pet 的保存位置也会检查全部显示器的 `availableGeometry()`；显示器配置变化导致旧位置失效时，会自动回到主屏右下角。

目标继续覆盖：

- 主屏 / 副屏；
- 副屏在主屏左侧或右侧；
- 100% / 150% / 200% Windows 缩放。

## 应用图标

`tools/build_app_icon.py` 会从最终 `walk.png` 第 9 帧自动裁取正面 Q 版头像，生成多尺寸 `build/app.ico`。

打包版将它用于 EXE、右键菜单和系统托盘。源码模式如果还没生成 `.ico`，程序会直接从 Walk 第 9 帧现场生成 Qt 图标作为兜底。

## 开发入口

动画演示：

```powershell
python main.py --demo
```

Kick 命中校准：

```powershell
python main.py --calibrate-kick
```

这两个入口保持独立，不接入常驻单实例，避免开发工具受后台 Pet 干扰。

## 打包

```powershell
pip install -r requirements.txt
.\build.ps1
```

输出：

```text
dist\叫家琦来.exe
```

CI 会在 Windows 上实际执行同一套 onefile 构建，并保留短期 `JiaqiCleaner-Windows` 构建产物。

## 测试

```powershell
pip install -r requirements-dev.txt
python -m pytest -q
```

`pytest.ini` 继续明确排除旧的手工 `test_uiauto.py`，但现在会运行所有维护中的回归套件，包括：

- 精灵图标准帧结构；
- 走路相位、等待位与攻击位；
- 异步删除；
- Windows HRESULT 错误分类；
- 失败恢复 / 重试 / 快速溜走；
- 右键菜单注册；
- 单实例 IPC 协议；
- 常驻随机互动 Provider；
- PetWidget Qt 离屏烟测；
- Kick 校准器与基础 Qt 构建。

## 项目结构

```text
app/
  autostart.py           Windows 开机启动
  character.py           角色参数与锚点配置
  chibi_avatar.py        精灵播放器与动作状态机
  context_menu.py        文件 / 文件夹右键菜单
  delete_service.py      回收站、错误分类与 Shell 刷新
  delete_task.py         后台删除 QRunnable
  interactions.py        Pet 互动 Provider 接口与随机吐槽
  pet_widget.py          常驻小人、拖动与气泡
  resident_controller.py 常驻生命周期、托盘、任务 session
  responsive_overlay.py  非阻塞删除动画 Overlay
  single_instance.py     QLocalServer / QLocalSocket IPC
  overlay.py             多屏舞台与主动画流程
characters/jiaqi/
  character.json
  sprites/
    walk.png
    kick.png
    victory.png
tools/
  build_app_icon.py
main.py
build.ps1
```

当前不计划加入音效，先把常驻、真实目标识别和日用体验做稳。
