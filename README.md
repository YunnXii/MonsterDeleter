# 叫家琦来：桌面文件清理小剧场

这是从 `MonsterDeleter` 改造而来的 Windows 桌面互动工具。右键选择一个文件或文件夹后，Q 版家琦会从屏幕边缘走到目标旁边，确认一下，然后一脚把它踢进回收站。

## 当前角色

最终角色采用统一生成并加工后的 Q 版逐帧精灵：

- 短黑发、黑色矩形眼镜；
- 灰色日常 Polo 衫、深色长裤、浅灰运动鞋；
- 冷静、斯文、略带一点拽感的“冷面执行官”气质；
- 三套动作资源：走路、踢击、扶眼镜收尾。

走路并不是把整张图机械循环，而是按腿部相位重新剪辑：

```text
起步：1 → 2 → 3
巡航：4 ↔ 3
停车请求：等待第 3 帧结束
收步：6 → 7 → 8 → 9
```

这样角色可以始终从屏幕边缘出现，长距离行走时用第 3 / 4 帧左右腿交替，接近目标后再自然减速、收腿并站稳。

## 使用

### 源码运行

```powershell
pip install -r requirements.txt
python main.py --demo
```

演示模式只播放动画，不会删除内容。

正常运行：

```powershell
python main.py
```

程序会注册 Windows 右键菜单“叫家琦来收拾它”，随后启动安全演示。之后右键任意文件或文件夹即可使用。

也可以明确注册或移除菜单：

```powershell
python main.py --install-menu
python main.py --uninstall-menu
```

### 测试

```powershell
pip install -r requirements-dev.txt
python -m pytest -q
```

### 打包

```powershell
.\build.ps1
```

生成文件位于 `dist\叫家琦来.exe`。

## 交互流程

1. 右键选择文件或文件夹；
2. 点击它在屏幕上的位置；
3. 家琦从屏幕边缘走入，并自动朝向目标；
4. 接近目标时等待正确腿相位，再播放收步动作并站稳；
5. 点击“对，收拾它”；
6. 踢击第 5 帧命中时，目标被移入回收站并播放爆炸；
7. 踢完后播放扶眼镜、微笑、恢复冷脸的收尾动作；
8. 点击“等等，我点偏了”可重新选择舞台位置，`Esc` 可随时退出。

点击位置只用于安排动画舞台，真正处理的目标始终是右键菜单传入的路径，避免误删旁边的图标。

## 项目结构

```text
app/
  character.py       角色参数与锚点配置
  chibi_avatar.py    精灵播放器与动作状态机
  context_menu.py    文件和文件夹右键菜单
  delete_service.py  回收站操作
  explosion.py       爆炸效果
  overlay.py         全屏交互、人物位移与动作流程
characters/jiaqi/
  character.json     人物尺寸、速度、命中锚点和台词
  sprites/
    walk.png          9 帧走路素材
    kick.png          8 帧踢击素材
    victory.png       6 帧扶眼镜收尾素材
main.py               程序入口
build.ps1             Windows 打包脚本
```

## 下一步

- 实机微调走路速度、停步距离和各帧停留时间；
- 校准不同 DPI / 多显示器环境下脚尖与目标的落点；
- 增加可选音效和更细的命中反馈。
