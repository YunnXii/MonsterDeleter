# 叫家琦来：文件清理小剧场

这是从 `MonsterDeleter` 改造而来的 Windows 文件清理工具。右键选择一个文件或文件夹后，Q 版家琦会走到目标旁边，确认一下，然后一脚把它踢进回收站；命中瞬间，目标的系统图标还会按抛物线旋转飞出屏幕。

动画已经按当前素材封版，后续开发重点转向真正的日用体验：首次运行、右键菜单、失败重试、多显示器、DPI、Shell 刷新和单 EXE 打包。

## 首次运行

直接双击程序：

```powershell
python main.py
```

或双击打包后的 `叫家琦来.exe`。

程序会自动检查当前用户的文件 / 文件夹右键菜单：

- 首次运行时自动安装“叫家琦来收拾它”；
- 如果 EXE 或源码目录换了位置，再次双击会自动修复注册表里的旧路径；
- 正常双击不会突然全屏播放动画，而是显示一个极简提示；
- 可选择“先演示一下”或“移除右键菜单”。

右键菜单写在 `HKEY_CURRENT_USER`，不要求管理员权限。打包版菜单图标直接使用程序自身的 Q 版头像图标。

也可以显式执行：

```powershell
python main.py --install-menu
python main.py --uninstall-menu
```

## 正常使用

1. 右键一个文件或文件夹，选择“叫家琦来收拾它”；
2. 点击它当前在屏幕上的位置；
3. 家琦从目标所在显示器的边缘走入；
4. 停到更自然的等待位并正面确认；
5. 点击“嘤嘤嘤，就是这个！”后，转身向前半步并开踹；
6. Kick 第 5 帧真正执行回收站操作；
7. 成功时爆炸、系统图标替身飞出屏幕，并显示“这倒霉文件已经踹飞了。”；
8. 最后扶眼镜、微笑、恢复冷脸后离场。

点击位置只负责动画舞台。真正处理的对象始终是右键菜单传入的完整路径，避免误删旁边的图标。

## 删除失败

删除失败不会继续假装成功：不会播放爆炸、不会让图标飞走，也不会播放得意的胜利收尾。

底层会按 Windows 错误码 / HRESULT 区分常见情况：

- 文件正在被占用；
- 权限不足；
- 文件已经不存在；
- 其他回收站错误。

文件占用时显示：

```text
这玩意正开着呢，踹不动。

[关了再踹一次]  [不踹了]
```

关闭 Word、播放器或其他占用程序后，可以直接原地“再踹一次”，不会重新走完整段入场动画。

删除成功后还会额外通知 Windows Shell 刷新对应路径，尽量避免 Explorer 原图标慢半拍还留在原地。

## 多屏与 DPI

选择目标位置时覆盖整个虚拟桌面；点击目标后，动画舞台会立刻锁定到目标所在显示器。后面的入场、站位、踢击、对话框和离场都使用该显示器自己的 Qt 逻辑坐标。

程序启用了 Qt High-DPI `PassThrough` 策略，目标是同时覆盖：

- 主屏 / 副屏；
- 副屏位于主屏左侧或右侧；
- 100% / 150% / 200% Windows 缩放。

这部分仍需要 Windows 实机继续做组合验收，但代码不再按整个虚拟桌面的中心猜人物方向。

## 动画导演（封版）

```text
起步：1 → 2 → 3
巡航：3 → 6 → 4 → 2 → 循环
停车：提前预约第 3 帧合法停车相位
收步：6 → 7 → 8 → 9
等待：第 9 帧正面 + 1px 呼吸，停在攻击位外侧 40px
确认：9 → 8 → 7，同时前移 40px
攻击：转身完成 + 前移完成 → Kick
命中：Kick 5 → 回收站 + 爆炸 + 图标抛飞
收尾：扶眼镜 → 微笑 → 冷脸
```

关键参数：

- 行走速度约 `390 px/s`；
- 巡航 `105 / 85 / 105 / 85ms`；
- Kick 锚点 `impact_x=234 / impact_y=136`；
- 等待位额外外移 `40px`；
- Kick 第 5 帧是唯一命中帧。

如需重新校准：

```powershell
python main.py --calibrate-kick
```

## 图标抛飞

不会直接移动 Explorer 的真实桌面图标。程序会在删除前读取文件或文件夹的系统图标，删除成功后再生成一个透明图标替身：

- 水平初速度约 `1050 px/s`；
- 向上初速度约 `680 px/s`；
- 重力约 `1650 px/s²`；
- 自旋约 `720°/s`；
- 飞出舞台后自动销毁。

`--demo` 模式会完整演示动画与图标抛飞，但不会删除任何内容：

```powershell
python main.py --demo
```

## 应用图标

不额外维护另一套 Logo。`tools/build_app_icon.py` 会从最终 `walk.png` 第 9 帧自动裁取正面 Q 版头像，生成多尺寸 `build/app.ico`。

这个图标会同时用于：

- `叫家琦来.exe`；
- Windows 右键菜单；
- 首次运行 / 状态窗口。

## 打包

```powershell
pip install -r requirements.txt
.\build.ps1
```

脚本会先生成头像图标，再使用 PyInstaller 打成单文件：

```text
dist\叫家琦来.exe
```

CI 也会在 Windows 上实际执行同一套构建，并保留短期 `JiaqiCleaner-Windows` 构建产物，避免“源码测试通过但最后 EXE 打不出来”。

## 测试

```powershell
pip install -r requirements-dev.txt
python -m pytest -q
```

当前回归覆盖包括：

- 精灵图标准帧结构；
- 走路相位和等待 / 攻击位；
- Kick 命中只触发一次；
- 图标抛体运动；
- 删除失败分类与 Windows HRESULT；
- 文件占用时的最终文案和按钮；
- Windows 右键菜单注册 / 检查 / 清理；
- Qt 离屏构建与校准器。

## 项目结构

```text
app/
  character.py       角色参数与锚点配置
  chibi_avatar.py    精灵播放器与动作状态机
  context_menu.py    右键菜单安装、检查与自动修复
  delete_service.py  回收站、错误分类与 Shell 刷新
  explosion.py       爆炸效果
  flying_icon.py     系统图标捕获与抛体飞行
  kick_calibrator.py Kick 可视化命中校准器
  launcher.py        首次运行 / 菜单状态提示
  overlay.py         多屏舞台、人物位移、成功 / 失败交互
characters/jiaqi/
  character.json     人物尺寸、速度、等待位和命中锚点
  sprites/
    walk.png
    kick.png
    victory.png
tools/
  build_app_icon.py  从正面精灵自动生成应用图标
main.py               程序入口
build.ps1             Windows 单文件构建
```

当前不计划加入音效，先把核心日用体验做稳。
