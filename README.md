# FF14 音效技能栏

Windows 音效工具。为 FF14 的技能键配上自定义声音，也可通过分页轮盘手动播放。本仓库对应 v1.0.1，基于原项目 v1.0 增加多音效绑定。功能包括前台及后台触发、窗口置顶、能力技独立冷却、临时 GCD、截图核对、配置套装和虚拟声卡输出。

- 实际按键只触发音效，不修改游戏里的键位。普通技能的播放冷却默认 2.5 秒，能力技每格单独防连按 1 秒。
- 每个技能格可绑定多个音效，选择列表循环或随机播放。技能键与轮盘共享该格的循环进度。
- 默认长按 Y 打开轮盘，滚轮切页，松手播放。可在「技能栏」打开「窗口置顶」或「只播放轮盘音效」。
- 支持批量导入音频、试听、组合、变调变速和导出诊断日志。音效可在本机播放，也可通过另行安装的虚拟声卡送进语音。

[详细使用教程](docs/usage.md) · [黑魔高手的哔哩哔哩主页](https://space.bilibili.com/1603158)

## 从源码运行

使用 Windows 10 或 11，推荐 64 位 Python 3.13。在项目目录打开 PowerShell：

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe ff14_app.py
```

首次启动后，进「音效库」导入自己的声音，再给技能格设快捷键并绑定。数据默认保存在 `%LOCALAPPDATA%\FF14Soundbar`。需要无输入、无播放的离屏检查时运行：

```powershell
.\.venv\Scripts\python.exe ff14_app.py --check
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

## 可选资源

公开源码不包含游戏图标、截图样本、应用图片、梗音效和虚拟声卡驱动。手动设置键位、导入和绑定音效、冷却与轮盘可直接使用。

- **图标与截图识别**：从可使用的本地 FF14 7.05 素材中生成图标目录和 OCR 字形模板。缺少字形模板时可以手动补录键位，缺少图标目录时可以用空白技能格。
- **能力技自动识别**：可运行 `tools/prepare_action_types.py` 生成分类索引。没有索引时可以手动标记能力技。
- **虚拟声卡**：在 [VB-Audio 官网](https://vb-audio.com/Cable/)下载安装驱动，或使用已安装的兼容虚拟声卡。配置见使用教程。

准备本地图标和字形模板的示例：

```powershell
.\.venv\Scripts\python.exe -m pip install Pillow
.\.venv\Scripts\python.exe tools/prepare_skillbar_assets.py "D:\FF14素材" assets/ff14
.\.venv\Scripts\python.exe tools/prepare_key_glyphs.py "D:\FF14素材" assets/ocr
.\.venv\Scripts\python.exe tools/prepare_action_types.py
```

## 打包 Windows 程序

```powershell
.\.venv\Scripts\python.exe -m pip install pyinstaller
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm FF14Soundbar.spec
```

生成文件位于 `dist/`。构建会纳入存在的本地可选资源。向他人分发时，只使用有权分发的图标、音频和驱动，并保留适用的许可证与说明。

## 署名与许可证

本项目由黑魔高手在 ChiZhou（迟昼）的 [SR Voiceover Roulette](https://github.com/ChiZhou6/SR-Voiceover-Roulette) 基础上修改。代码采用 [MIT License](LICENSE)。第三方软件和素材适用各自的授权，FF14 相关权利归其权利人。
