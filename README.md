# 叫家琦来：桌面文件清理小剧场

这是从 `MonsterDeleter` 改造而来的 Windows 桌面互动工具。右键选择一个文件或文件夹后，Q 版家琦会走到目标旁边，确认一下，然后一脚把它踢进回收站。

## 当前版本的角色形象

第一版没有继续沿用怪兽逐帧素材，而是根据照片特征制作了一个程序内绘制的 Q 版矢量角色：

- 短黑发，顶部蓬松并略向一侧梳；
- 黑色矩形眼镜，带暖金色镜桥和镜腿；
- 灰色日常 Polo 衫；
- 两头半左右的 Q 版比例；
- 支持走路、待机、蓄力踢击和胜利动作。

矢量角色由 PyQt6 实时绘制，因此没有绿幕边缘、透明 PNG 毛边或 AI 连续帧变脸问题，也能自然适配不同 DPI。

## 使用

### 源码运行

```powershell
pip install -r requirements.txt
python main.py --demo
```

演示模式只播放动画，不会删除内容。

双击运行：

```powershell
python main.py
```

程序会注册 Windows 右键菜单“叫家琦来收拾它”，随后启动安全演示。之后右键任意文件或文件夹即可使用。

也可以明确注册或移除菜单：

```powershell
python main.py --install-menu
python main.py --uninstall-menu
```

### 打包

```powershell
.\build.ps1
```

生成文件位于 `dist\叫家琦来.exe`。

## 交互流程

1. 右键选择文件或文件夹；
2. 点击它在屏幕上的位置；
3. 家琦从空间更充足的一侧走入，并自动朝向目标；
4. 点击“对，收拾它”；
5. 踢击命中时，目标被移入回收站；
6. 点击“等等，我点偏了”可重新选择舞台位置，`Esc` 可随时退出。

点击位置只用于安排动画舞台，真正处理的目标始终是右键菜单传入的路径，避免误删旁边的图标。

## 项目结构

```text
app/
  character.py       角色配置读取
  chibi_avatar.py    Q 版角色与动作绘制
  context_menu.py    文件和文件夹右键菜单
  delete_service.py  回收站操作
  explosion.py       程序绘制的爆炸效果
  overlay.py         全屏交互和动作流程
characters/jiaqi/
  character.json     人物外观、台词和尺寸配置
main.py               程序入口
build.ps1             Windows 打包脚本
```

## 下一步

- 增加可选音效；
- 用设置界面调整台词、角色尺寸和走路速度；
- 增加“红笔退稿”等第二套动作；
- 在多显示器和 125% / 150% 缩放环境继续实机校准脚部落点。
