# 手机客户端设计(Expo / React Native,iOS 先走 TestFlight)

> 日期:2026-10-04。由用户授权"自己推进、无需逐步批准"。这份文档记录我做的设计决定、依据和**没有验证的部分**。
> 标记:✅ 已验证(本机命令/源码核对)/ 🏷 官方页面或包元数据 / ⚠ 未验证。

## 1. 范围

要做的客户端 = 语音交互(P1)+ 摄像头变焦(P2)+ 最小的引导层(P3,只做"分类 + 固定话术")。
**不做 P4(盲道/盲人行走引导)**:这需要专门的盲道与障碍感知和实地测试,VLM 单独做不到(见 §6)。
本应用**不是安全设备**,界面和朗读里都要有固定的"仅供参考"说明。

## 2. 用户已确定的决定(本次对话)

- 话术:**建议性为主**——"可能/似乎";高危类只用固定、审核过的短提示;不说"快跑",不给路线,不说"安全";信息不足就说看不清。
- 语言:**中英双语**;语音识别一次只用一个语言,设置里选择并在主界面可一键切换(v1 不做自动判断)。
- 唤醒:**按住说话**(Push-to-talk);应用自己的朗读不会被当成命令。
- 模型位置:**本地 AI / 远程服务器可切换,默认本地**。
- 栈:Expo + TypeScript;iOS 先用 TestFlight 测试;后续 Android。环境沿用本机已有的 Node 24、eas-cli 24.7、Android SDK 与模拟器。

## 3. 技术选型(版本均于 2026-10-04 查 npm 注册表,🏷)

| 用途 | 选择 | 说明 |
|---|---|---|
| 框架 | Expo SDK 57(`expo` 57.0.26)、React Native 0.87.1、TypeScript | `latest` 标签 |
| 相机与变焦 | `expo-camera` 57 | `zoom` 属性 0–1,走设备硬件变焦(比笔记本摄像头的数字裁剪更接近"看清物体") |
| 朗读 | `expo-speech` 57 | iOS 系统语音,免费、离线 |
| 语音识别 | `expo-speech-recognition` 57.1.0(MIT) | 封装 iOS `SFSpeechRecognizer` / Android `SpeechRecognizer`,支持按键开始/停止、端侧识别(视语言和系统而定);**需要开发构建,不能用 Expo Go** |
| 本地模型 | `llama.rn` **0.12.9(稳定版,锁定)** | ✅ 解包源码确认其内置 mtmd 含 `clip_graph_minicpmv4_6`,即支持 MiniCPM-V 4.6;`latest` 标签指向候选版 0.13.0-rc.6,**不用** |
| 密钥存储 | `expo-secure-store` | 保存远程服务器 API Key |
| 图片处理 | `expo-image-manipulator` | 缩到最长边 640 并转 JPEG |
| 设置持久化 | `@react-native-async-storage/async-storage` | 非敏感设置 |

## 4. 架构

```
src/
  settings/    设置模型 + 校验 + 持久化(API Key 走 SecureStore)
  safety/      命令式用语拦截(移植 Python 引擎的 _COMMAND_PATTERN 并补中文)、固定话术表、播报策略
  prompts/     中英提示词 + 结构化输出 schema
  providers/   VisionProvider 接口;remote(OpenAI 兼容 /v1/chat/completions);local(llama.rn);模型下载管理
  voice/       命令解析(纯函数,中英词表)、识别封装、朗读封装
  camera/      变焦档位(纯函数)
  controller/  分析流程编排(一次只处理一个请求;新操作打断旧朗读;失败重试策略)
  ui/          主界面(预览、按住说话、分析、放大/缩小、结果)与设置界面
```

**关键设计:模型只做分类,话术由 App 说。** 模型返回结构化 JSON:
`{ answer, scene, hazard, hazard_confidence }`(`scene`、`hazard` 为枚举)。`answer` 是对画面的事实描述,先过命令式用语拦截;
危险与场景提示一律从**固定话术表**按枚举取,模型不能自由生成"该怎么做"。理由:本项目实测里模型会漏看车辆、凭空说"有人"、
对特定输入输出乱码,不能让它直接决定对用户说什么行动话。

**播报规则:** 置信度低或 `unclear` → 说"画面或光线不足,无法判断";`hazard=none` 时**不说"安全"**,只说"这一帧里没有看到明显危险迹象,不能代替你自己的判断";
免责声明在界面常驻、每个会话首次分析时朗读一次。

**失败与重试:** 非法 JSON(包括 Ollama 对特定图片×尺寸的确定性乱码)→ 换尺寸重试一次(最长边 640 → 592),仍失败则如实告知并不朗读猜测;
网络超时/鉴权失败 → 明确提示,不静默回退到另一个提供方(避免画面悄悄发往别处)。

## 5. 提供方与隐私

- **远程**:`POST {baseUrl}/v1/chat/completions`,`response_format: json_schema`,可选 `Authorization: Bearer`。兼容 llama-server(可用其 `--api-key`)和 Ollama 的 /v1。
  切到远程时首次需确认"画面将发送到你配置的服务器";界面始终显示当前模式。生产环境必须 HTTPS(iOS ATS);仅对局域网放行 `NSAllowsLocalNetworking`。
- **本地**:llama.rn 加载 `MiniCPM-V-4.6-Q4_K_M.gguf`(529,101,536 B)+ `mmproj-MiniCPM-V-4.6-Q8_0.gguf`(727,954,528 B),`ctx_shift:false`、`enable_thinking:false`。
  模型首次从 Hugging Face 下载(Wi-Fi 提示),下载后校验文件大小;⚠ 设备上没有做 SHA-256 校验(JS 端无法流式哈希 1 GB 文件)。
- 默认本地:画面不离开手机。语音识别优先使用系统端侧识别,是否真正离线取决于语言包和系统,**不作保证**。

## 6. 为什么不做盲道引导(P4)

模型能描述,但给不出可靠的位置、方向和距离;"沿盲道走"需要盲道分割 + 深度/障碍检测,并且必须与盲人用户/机构做实地测试。
单靠提示词做这件事可能把人引向危险。该方向作为独立研究线保留在路线图里,不在这个 App 的宣传和界面文案里出现"导航"。

## 7. 构建与发布(谁做什么)

- 我做:项目代码、测试、`app.config`、`eas.json`(development / preview / production)、文档;Android 在本机模拟器验证。
- **用户做**(账号、付费、凭据,我不会代做):Expo 账号登录(`eas login`)、Apple Developer 账号与 App Store Connect 的 App 记录、bundle ID 确认、
  `eas build -p ios --profile production` 与 `eas submit`(TestFlight)。`WUVA_APP\BACKUP` 里有一个 Apple 的 `.p8` 私钥文件,**我没有读取或使用**,请保持在仓库之外。
- 本机是 Windows,**无法本地构建或运行 iOS**;iOS 只能经 EAS 云构建,所以 iOS 行为在你测试之前**全部未验证**。

## 8. 验证计划与已知风险

- 自动化:Jest(命令解析、拦截、话术映射、变焦、设置校验、远程提供方的请求/解析/超时/重试、控制器流程)、`tsc --noEmit`、ESLint、`expo-doctor`、`expo export` 打包。
- Android 模拟器冒烟:远程提供方指向本机 llama.cpp(模拟器里 `10.0.2.2`),验证"拍一帧 → 模型 → 播报"端到端。
- ⚠ 未验证:本地模型在真机上的速度与内存(iPhone 内存、Metal)、`expo-speech-recognition` 的中文端侧识别、TestFlight 构建本身、真实远程服务器的 HTTPS 部署。
- ⚠ 风险:`llama.rn` 与 MiniCPM-V 4.6 的组合只在源码层面确认支持,没有任何设备实测;老 iPhone 可能放不下约 1.3 GB 模型。
