# Visual Helper(手机客户端)

用手机相机"看周围",用语音操作并朗读结果。AI 可以在**手机本机**运行,也可以切换到你自己的**远程服务器**(例如我们测试过的 GPU 机器)。
技术栈:Expo SDK 57、React Native 0.86、TypeScript、expo-router。设计决定与依据见
[`docs/superpowers/specs/2026-10-04-mobile-app-design.md`](../docs/superpowers/specs/2026-10-04-mobile-app-design.md)。

> **这不是安全设备,也不是导航工具。** 描述由 AI 生成,可能看错、漏看;单帧画面不能说明周围是否安全。
> 它不能代替你自己的判断、白手杖、导盲犬或他人的帮助。盲道/行走引导**没有实现**,也不应从这个应用里推断出来。

## 现在能做什么 / 验证到什么程度

| 功能 | 状态 |
|---|---|
| 按住说话(中英),命令:看看周围 / 放大 / 缩小 / 还原 / 重复 / 停止 / 切换语言 | 命令解析:✅ 单元测试;语音识别本身:⚠ 未在真机验证 |
| 相机硬件变焦(`expo-camera` 的 `zoom`) | ⚠ 未在真机验证 |
| 朗读结果(系统语音),中英 | ⚠ 未在真机验证 |
| **远程服务器**:OpenAI 兼容 `/v1/chat/completions`,可带访问密钥 | 请求/解析/超时/错误映射:✅ 单元测试;⚠ 真实服务器见下方"Android 模拟器验证" |
| **本机 AI**:`llama.rn` 0.12.9 + MiniCPM-V 4.6(约 1.26 GB,首次下载) | 逻辑:✅ 单元测试;应用内下载 1.26 GB 并按字节校验:✅ 在模拟器上走通;模型能载入并开始推理:✅ 在 x86 模拟器上;**真手机上的速度、内存:⚠ 完全未验证**(见下方"本机推理在模拟器上的实测") |
| 本机推理超时、等待秒数、取消按钮 | ✅ 单元测试(超时、载入也计入超时、取消优先);✅ 在模拟器上看到超时提示。默认 120 秒后停止并建议改用远程服务器 |
| 话术安全:模型只描述并标注危险类别,提示语来自固定话术表;拦截命令式用语、**安全断言**("环境安全/无危险")和提示词泄漏;不说"安全"、不说"跑"、**不做任何宽慰** | ✅ 单元测试 + 对真实模型的实时测试(见下) |
| **危险提示**(车辆/水边/落差/拥挤/动物/火烟/障碍) | ⚠ **实验性,召回率未知**:在 12 张公开图上模型一次都没有标出危险(包括有卡车的街景),我没有带真实危险的公开图可测。没有提示 ≠ 没有危险 |
| "海滩→玩、好环境→享受"等**场景友好提示** | ❌ **已删除**:场景标签约一半是错的,不可靠 |
| iOS | ⚠ 本机是 Windows,无法运行 iOS;JS 包可以打出来,其余等你的 TestFlight 测试 |

## 用真实模型验证过的事(2026-10-04,MiniCPM-V 4.6 + llama.cpp,12 张公开 COCO 图,中英各一轮)

实时测试 [`remote.live.test.ts`](src/providers/__tests__/remote.live.test.ts)(默认跳过,设 `LIVE_LLAMA_URL` 才运行)用应用自己的提供方代码对真实服务器发请求:

| 项目 | 结果 |
|---|---|
| 结构化输出有效 | 英文 12/12,中文 11/12(1 次无效输出,应用会换尺寸重试一次) |
| **中文回答** | 英文提示词要求"用中文回答" → 汉字占比 **0%**;**整段提示词用中文写 → 中位数 89%**。所以中文用中文提示词 |
| **模型违反"不要做安全判断"** | 11 条中文回答里 **8 条**带"没有明显危险/无危险";拦截后朗读的内容里没有。英文 0 条 |
| 提示词泄漏 | 早期提示词里写了"使用者视力不好",模型把它写进了描述 → 已从提示词中删除,并加拦截 |
| 场景标签 | 约一半错误,**已删除**(原设计里的 `scene`、`hazard_confidence`) |
| 危险标注 | 12/12 都是 `none`,**无法证明它有效** |
| 速度 | 本机核显 llama.cpp 约 8 秒/次(含约 1.2 GB 的模型、较长的提示词);手机上的速度**没有测过** |

### Android 模拟器里走过的界面流程(Expo Go SDK 57,Android 14 x86_64 虚拟设备 `Wuva_API34`,虚拟场景相机)

重启后内存够用,走通了(截图在 `outputs/mobile-smoke/`,被 git 忽略):

| 步骤 | 结果 |
|---|---|
| 应用启动、主界面 | ✅ 中文界面、模式标识、变焦百分比、常驻免责声明;预览显示虚拟客厅 |
| 放大 / 还原按钮 | ✅ "变焦 16%" → "变焦 0%";⚠ 虚拟相机不支持变焦,画面不变,**真实变焦效果要在真机上看** |
| 设置 → 远程服务器 → 同意对话框 → 填 `http://10.0.2.2:18937` → 测试连接 | ✅ "连接正常"(连到我这台电脑上的 llama.cpp) |
| 回主界面 | ✅ 模式标识变为"远程服务器",并显示"远程模式:画面会发送到你设置的服务器" |
| 看看周围(拍照 → 缩放到 640 → 发给模型 → 解析 → 拦截 → 显示) | ✅ 链路走通:显示中文描述、一句固定的"无法判断"提示、"远程 · 耗时 13.3 秒" |
| 第一次请求 | 超过当时的 30 秒超时 → 显示"服务器响应太慢,请稍后再试",没有崩溃(已把默认超时改为 60 秒) |
| 按住说话(Expo Go 没有语音识别原生模块) | ✅ 显示"此设备或此版本暂不支持语音识别,请用按钮操作",应用不崩溃 |
| 设置里的本机模型区域 | ✅ 显示"还没有下载",并因为虚拟设备只有 2 GB 内存而提示"内存可能太小,不建议使用本机 AI(估算,未实测)" |

**这次测试的限制(如实):** 模拟器的**拍照**输出的是一张几乎全黑的图(平均亮度 1.5/255,而实时预览是亮的),所以模型说"画面较暗",
应用读出固定的"无法判断"——行为正确,但**没能展示带真实内容的界面结果**(真实内容的结果见上面的实时模型测试)。
另外这个虚拟设备默认没有相机(`hw.camera.back=none`),我用启动参数临时加了虚拟场景相机,没有改你的 AVD 配置。
**没有验证:** 朗读出声(模拟器 `-no-audio`)、语音识别、相机硬件变焦、`llama.rn` 本机推理、相机权限被拒绝的界面、iOS。

### 本机推理在模拟器上的实测(2026-10-04,原生调试包,Android 14 x86_64,2 vCPU、4 GB 内存、无 GPU)

| 项目 | 结果 |
|---|---|
| 点击后载入模型 + 图像模块 | 约 52 秒(模型 16 秒,mmproj 23 秒起,合计到开始处理前) |
| 152 个文本 token 的预处理 | 64 秒 |
| 第一张图片块(63 token) | 约 210 秒;第 3 个块开始后 2.4 分钟仍未结束,整张图共 7 个分块,**我手动结束时已超过 10 分钟** |
| 对照 | 同一模型在这台电脑的 CPU 上用 llama.cpp 处理一张 640 档图约 13.6 秒([延迟分布 §3.4](../docs/latency-distribution-2026-10-03.md)) |
| 崩溃 / 内存不足被杀 | **没有**:进程一直存活,系统日志无 tombstone、无 lmkd 记录 |

- 用户先前报告的"点了之后应用崩溃":日志显示是一次从屏幕左边缘滑入的**返回手势**(09:16:32,不是我发的输入)把应用退到桌面,约 14 秒后系统把后台进程冻结,推理随之停住。不是应用崩溃。
- **没有查清为什么比电脑 CPU 慢这么多**(假设:2 个 vCPU 且负载 5.9、x86 模拟器上的指令集、内存换页);所以**这个数字不能代表真手机**,也不能用来下"本机不可行"的结论——只能说"在这个模拟器上不可用,真手机未测"。
- 当时的应用没有超时、没有进度提示:界面停在"正在看…",看上去像死机。现已加:等待秒数、本机首次载入提示、"看看周围"在等待期间变成"取消"、120 秒超时后提示改用远程服务器。

### 在模拟器里用电脑摄像头 + 本机服务器测远程模式

模拟器默认用虚拟 3D 房间当相机(画面几乎不变),不是你的摄像头。想用 Win11 摄像头:

```powershell
& "$env:LOCALAPPDATA\Android\Sdk\emulator\emulator.exe" -webcam-list                       # 找到名字,例如 webcam0
& "$env:LOCALAPPDATA\Android\Sdk\emulator\emulator.exe" -avd Wuva_API34 -no-snapshot-save -no-audio `
    -gpu swiftshader_indirect -memory 3072 -camera-back webcam0 -camera-front emulated
adb reverse tcp:8081 tcp:8081                                                                # 重启模拟器后需要重设,否则调试包连不上 Metro
.\scripts\cloud\start_local_llama.ps1                                                        # 主机上的 llama-server(核显,仅回环地址 127.0.0.1:18937)
```

应用里:设置 → 远程服务器 → 同意 → 地址填 `http://10.0.2.2:18937`(`10.0.2.2` 是模拟器看到的电脑本机)→ 测试连接。画面只在这台电脑内部流动。
内存提示:模拟器约占 4–5 GB,llama-server 约 1.5–2 GB;主机空闲内存不足时先关模拟器再启动服务器。

**这次测试发现并修复的应用缺陷:** 设置页的地址、密钥、模型名只在输入框"失焦"时才保存,在输入后直接点"返回"会丢失,于是主界面报"远程服务器还没设置好"。现在边输入边保存(并把设置更新串行化,避免两次快速更新互相覆盖)。⚠ 这一处只有真机/模拟器手动验证,没有单元测试(项目里没有组件测试框架)。

## 开发(Windows)

```powershell
cd mobile
$env:Path = "C:\Windows\System32;" + $env:Path   # 重要:见下方"已知坑"
npm install
npm test            # Jest
npm run typecheck   # tsc --noEmit
npm run lint        # expo lint
npx expo-doctor
npx expo export --platform android --output-dir ..\outputs\mobile-export-android   # 打包自检
```

**已知坑:** 这台机器的 `PATH` 里 Git 自带的 GNU `tar` 排在 Windows 自带 `tar` 前面,`llama.rn` 安装后脚本解压原生库时会把 `C:\...` 当成远程主机而失败
(`Cannot connect to C`)。安装前把 `C:\Windows\System32` 放到 `PATH` 最前面即可。EAS 云构建在 Linux 上,不受影响。
`llama.rn` 在安装时会从它的 GitHub Release 下载预编译的原生库(带 SHA-256 校验);偶尔 GitHub 返回 500,重试即可。

## 运行

- **原生模块(语音识别、`llama.rn`)不能用 Expo Go。** 完整功能需要开发构建:`npx expo run:android`(本机,需要 Android SDK + JDK 17/21)或 `eas build --profile development`。
- 代码对这两个原生模块是**惰性加载**的:在没有它们的构建里(例如 Expo Go),应用照常启动,语音按钮提示"不支持",本机模式提示"模型未准备好"。

## iOS 与 TestFlight(需要你来做的部分)

我无法替你完成账号、签名和付费相关步骤。准备好后,在 `mobile` 目录:

```powershell
npx eas-cli@latest login          # 你的 Expo 账号
npx eas-cli@latest init           # 创建 EAS 项目,会把 projectId 写入配置
npx eas-cli@latest build -p ios --profile production    # 云构建;首次会让你登录 Apple 账号并生成/选择证书
npx eas-cli@latest submit -p ios --latest               # 上传到 App Store Connect,之后在 TestFlight 里添加测试员
```

- **Bundle ID:** `app.json` 里是占位的 `com.davyhan.visualhelper`(Android 包名同)。Bundle ID 全球唯一,如果被占用或你想用自己的域名,先改 `ios.bundleIdentifier` 和 `android.package`,再构建。App Store Connect 里需要先有对应 Bundle ID 的 App 记录。
- **首个 TestFlight 包用 `production` 配置。** `production-memory` 配置会额外给 iOS 加"增加内存上限"等权限(让大模型更不容易被系统杀掉),它要求你的 App ID 已开通对应能力,否则签名可能失败——所以默认关闭,`production` 能成功后再试。
- **`WUVA_APP\BACKUP\AuthKey_*.p8`** 是你的 Apple API 私钥,我没有读取或使用它。如果要用它做免登录提交,请按 EAS 文档配置,并且**不要放进任何 Git 仓库**(`.gitignore` 已忽略 `*.p8`)。
- 构建在云端的 Linux 上进行,所以 Windows 上 `iOS` 无法本地运行/调试;iOS 上的行为(相机、语音、`llama.rn`、内存)要靠 TestFlight 包来验证。

## 远程服务器

应用只要求一个 **OpenAI 兼容**的 `POST {地址}/v1/chat/completions`,支持图片(`image_url`,data URI)和 `response_format: json_schema`。
我们验证过的是 llama.cpp 的 `llama-server`(同一个服务器配置在 [`scripts/cloud/`](../scripts/cloud/))。

- **访问密钥:** `llama-server` 启动时加 `--api-key <密钥>` 即可要求 `Authorization: Bearer`;应用把密钥存在系统钥匙串里。
- **HTTPS:** iOS 默认禁止明文 http;公网地址必须 https(应用也会拒绝公网 http 地址)。局域网地址(`192.168.x.x`、`10.x`、`*.local` 等)可以用 http。
  最简单的做法是在服务器前放一个自动签发证书的反向代理(如 Caddy),再配合 `--api-key`;或者用 Tailscale 之类的私网。**这部分没有在真实服务器上验证过**,等你下次开 GPU 实例时一起测。
- **隐私:** 切到"远程服务器"时必须你点"同意"(画面会发往你设置的服务器);默认是本机模式。应用不会在远程出错时悄悄回退到本机,也不会反过来。
- 老的 Ollama 服务器:Ollama 也提供 `/v1/chat/completions`,但我们实测它对少数"图片×尺寸"组合会输出乱码;应用遇到无效输出会换尺寸重试一次,仍失败就如实告知。

## 目录

```
src/
  core/        类型、结构化输出 schema、提示词、结果解析
  safety/      命令式用语拦截、固定话术、播报策略
  voice/       命令解析(纯函数)、识别/朗读封装
  camera/      变焦档位
  image/       缩放与 JPEG 编码
  settings/    设置模型、URL 校验、钥匙串/本地存储
  providers/   remote、local(llama.rn)、模型下载、提供方选择
  controller/  一次分析的流程编排
  i18n/        中英文案
  state/       应用级状态
  app/         expo-router 路由(主界面、设置)
```

## 许可证

仓库根目录的 `LICENSE`(Apache-2.0)适用于本项目自己的代码。`mobile/LICENSE`(MIT,版权属于 Expo)是脚手架模板自带的许可文件,
只对应模板生成的文件(如 `assets/` 里的默认图标)。
