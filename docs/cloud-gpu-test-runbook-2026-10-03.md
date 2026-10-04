# 云 GPU 测试手册(2026-10-03)

> 目的:用一台**短租的 NVIDIA GPU 实例**回答目标文档里还没有数据的问题
> ([cost-balance-target-2026-10-03.md](cost-balance-target-2026-10-03.md) 的 H1–H4),并完成 AGENTS.md 第31条
> 审计里"更大模型的质量上限""GPU 上的速度/并发""bf16 与 Q4 的差别"这几行。
> 所有准备工作已在本机做完,租机后只剩"开机 → 跑 → 取回结果 → **销毁实例**",以减少计费时间。
>
> 状态标记:✅ 已验证 / 🏷 来自官方页面或元数据 / ⚠ 写好但**尚未在真实服务器上运行**。

## 1. 已经准备好的东西

| 东西 | 位置 | 状态 |
|---|---|---|
| 测试媒体(24 张 COCO val2017 图、4 个 NASA 公开视频、6 张合成圆图 + 1 个合成运动视频,附标注) | `outputs/testkit-cloud/`(git 忽略,31.5 MB) | ✅ 已下载并记录 sha256,`manifest.lock.json` |
| 媒体来源清单(URL、来源、许可备注) | [`scripts/testkit_sources.json`](../scripts/testkit_sources.json) | ✅ 已提交 |
| 服务器端安装脚本(Ollama v0.35.1、llama.cpp b11146 CUDA、MiniCPM-V 4.6 GGUF,全部固定版本 + sha256 校验,只监听 127.0.0.1) | [`scripts/cloud/setup_server.sh`](../scripts/cloud/setup_server.sh) | ✅ 2026-10-04 在腾讯云 T4 上跑过;首次运行发现并修了 3 个缺陷(cudart 包解压路径、只查 `llama-server` 不查 CUDA 后端库导致悄悄退回 CPU、预检把 404 当不可达),见 [T4 实测 §6](cloud-t4-results-2026-10-04.md);重复运行时磁盘预检会因已装完而不足,需 `MIN_FREE_GB=10` |
| 参数扫描用的重启脚本 | [`scripts/cloud/restart_llama.sh`](../scripts/cloud/restart_llama.sh) | ✅ 在 T4 上用过 |
| 客户端测试套件(经 SSH 隧道从笔记本发请求) | [`scripts/cloud/run_cloud_suite.py`](../scripts/cloud/run_cloud_suite.py) | ✅ 16 个单元测试(用假服务器);✅ 已对本机 Ollama(`--api ollama`)和本机 llama-server SYCL 版(`--api openai`,`/v1/chat/completions` + `json_schema`)各做过 t0/t1/t3 冒烟运行,结果见 [延迟分布文档 §3.7](latency-distribution-2026-10-03.md);⚠ 尚未对 CUDA 版 llama-server 和多模型/并发(t2/t4)在真实服务器上跑过 |
| 停止服务脚本 | [`scripts/cloud/stop_servers.sh`](../scripts/cloud/stop_servers.sh) | ⚠ 未在真实服务器上运行 |
| 费用/流量模型 | [`scripts/cost_model.py`](../scripts/cost_model.py) | ✅ |

服务器要下载的固定文件(🏷 2026-10-03 取自发布页元数据):Ollama 1439.7 MB、llama.cpp CUDA 12.8 包
168.9 MB(缺 CUDA 运行库时再下 594.4 MB)、MiniCPM-V 4.6 Q4_K_M 529.1 MB + mmproj Q8_0 728.0 MB;
可选 bf16 共约 2.6 GB。Ollama 的 qwen3-vl / minicpm-v4.5 模型体积我**没有核实**,总下载量以实际为准,
下载时间是本次最大的时间不确定项。

## 2. 隐私与安全规则(其中前三条由代码强制)

1. **只发送测试集里的公开/合成媒体。** 套件没有"指定任意图片"的选项,并会在启动时按 `manifest.lock.json`
   重新校验每张 COCO 图的 sha256,合成图必须在 `labels.json` 里;摄像头帧和 `videos/test_video.avi`
   (用户个人录像)**不会也不能**被它上传。
2. **基础 URL 必须是回环地址**(SSH 隧道的本地端);要连非回环地址必须显式加 `--allow-nonloopback`。
3. 某项测试连续 3 次请求出错就自动停止,不在坏掉的服务器上烧钱。
4. 把实例当作**不可信机器**:不放任何令牌/密钥/个人数据;SSH 不转发 agent(`ForwardAgent=no`);
   服务器上只 `git clone` 本项目的**公开**仓库;结果只回传到本机。
5. 模型服务只绑 `127.0.0.1`,不开放公网端口;用 SSH 隧道访问。
6. **我不会输入密码、API 密钥或付款信息**,也不会注册账号或下单;这些由用户完成。我只用用户给的
   **专用密钥文件路径**(不要把密钥内容贴给我)。
7. 一律使用专用密钥对,不要复用日常密钥。用户在笔记本上生成(私钥不离开本机):

```bash
ssh-keygen -t ed25519 -f ~/.ssh/vi_cloud -C "visualintel-cloud-test"
```

把 `~/.ssh/vi_cloud.pub` 的内容贴到云平台的"SSH 公钥"一栏即可。

## 3. 租机要求(建议,非购买授权)

- 1 张 NVIDIA GPU;跑到 qwen3-vl 8B 建议 ≥ 16 GB 显存,想顺带试 30B-A3B(`WITH_30B=1`,约 20 GB 权重)
  需要 ≥ 24 GB。更便宜的小卡也能跑 MiniCPM-V 4.6 部分,只是缺少大模型数据。
- Ubuntu 22.04/24.04 一类的 Linux 镜像,驱动能让 `nvidia-smi` 工作;有 `curl`、`zstd`(解 Ollama 包)。
- 磁盘:可用空间 ≥ 35 GB(脚本默认检查,`MIN_FREE_GB` 可调)。默认模型集约下载 19 GB(🏷 ollama.com 2026-10-03:
  minicpm-v4.6 1.6、qwen3-vl 2b/4b/8b 1.9/3.3/6.1、minicpm-v4.5 6.1)+ 压缩包约 2.2 GB + 解压后的 Ollama /
  llama.cpp(解压体积未测,按 ≤ 8 GB 估)+ GGUF 1.3 GB,合计约 30 GB。50 GB 若是**系统盘**,扣掉系统和驱动后可能不够;
  空间紧时设 `MODELS="minicpm-v4.6 qwen3-vl:2b-instruct qwen3-vl:4b-instruct"` 可少下 12 GB;
能 SSH 登录;出站可访问 github.com、
  huggingface.co、registry.ollama.ai(脚本会预检)。
- **候选实例(用户提供):腾讯云 GPU 计算型 GN7.2XLARGE32,1×T4 16 GB、8 vCPU、32 GiB。** 装得下 MiniCPM-V 4.6
  和 qwen3-vl 2B/4B/8B(Q4);装不下 30B-A3B,T4(Turing)没有原生 bf16,所以不要设 `WITH_30B=1` / `WITH_BF16=1`。
  这是云上很便宜的一档 GPU,数据可作为"最低成本档"的参照,不代表 4090/L4。实际价格、地域、是否竞价待用户确认
  (我只在第三方聚合站看到标准按量价约 7.81–8.68 元/小时,未核实,也不是"2折"后的价格)。
- **地域/镜像:** 若实例在国内,github.com / huggingface.co / registry.ollama.ai 可能很慢或不通
  (未核实)。`setup_server.sh` 的下载地址可用环境变量 `OLLAMA_URL`、`LLAMA_BASE`、`HF_BASE` 换成镜像;
  二进制和 GGUF 仍按固定 sha256 校验,但 `ollama pull` 的模型不在校验范围内。
- **镜像/驱动(用户下单页截图,2026-10-03):** Ubuntu Server 24.04 LTS、自动安装 GPU 驱动 580.126.20、CUDA 13.0.2、
  cuDNN 9.20.0。Ollama 文档写明支持计算能力 5.0+ 且驱动 ≥ 550(🏷 docs.ollama.com/gpu),T4(7.5)在内,驱动 580 满足。
  llama.cpp 请用默认的 **CUDA 12.8 包**(`LLAMA_CUDA=12.8`),不要选 13.4:驱动报告的是 CUDA 13.0,
  13.4 的包可能需要更新的驱动(推断,未验证)。llama.cpp master 的 CUDA 默认架构列表含 `75-virtual`
  (🏷 ggml/src/ggml-cuda/CMakeLists.txt;b11146 本身未逐行核对),也就是 T4 靠 PTX 即时编译运行:
  **首次加载模型会慢一些**,计时只统计热身之后的请求,首次加载时间另行记录。
- **llama-server 起不来不算安装失败:** 若启动失败,脚本会打印日志尾部并继续,只用 Ollama 路径测试(`--api ollama`)。
- 价格参考(🏷 runpod.io/pricing,2026-10-03 读取,USD/小时):RTX 4090 社区云 0.34、安全云 0.74,L4 0.44–0.49。
  其他平台未核实。**我无法控制计费**;预算上限 100 CAD/月只是调研约束,不是对具体消费的授权。
  估算:跑 2 小时按 0.74 USD/小时约 1.5 USD(≈ 2.1 CAD,汇率 1.4246),**加上存储/快照费**;
  时长本身是估计,首次运行可能更久。

## 4. 操作步骤

**用户做:** 创建实例(Spot 或按需均可)、贴入公钥、把以下信息发给我:GPU 型号与显存、平台名、
系统镜像、SSH 命令(主机/端口/用户)、**专用私钥文件路径**、每小时价格、是否已开快照。

**我做:**

```bash
# 0) 本机:确认仓库最新提交已推送(服务器克隆的是公开仓库)
# 1) 连接并安装(公钥认证,不转发 agent)
ssh -i <key> -p <port> -o IdentitiesOnly=yes -o ForwardAgent=no -o StrictHostKeyChecking=accept-new <user>@<host>
git clone https://github.com/davyhanbigtiger/Visual_Intelligence_Integration.git
bash Visual_Intelligence_Integration/scripts/cloud/setup_server.sh      # 可加 WITH_30B=1 / WITH_BF16=1
# 2) 本机另开窗口:建隧道(保持运行)。本机若已运行 Ollama(占用 11434),本地端口改用 21434 / 28080
ssh -N -L 21434:127.0.0.1:11434 -L 28080:127.0.0.1:8080 -i <key> -p <port> -o IdentitiesOnly=yes -o ForwardAgent=no <user>@<host>
# 3) 本机:跑套件(Ollama 路径;llama-server 路径见下)。价格币种不同(如人民币)时不要传 --price-per-hour,
#    它的字段名是 usd_per_1000_requests;事后用吞吐自行换算并标注币种
.venv\Scripts\python.exe scripts\cloud\run_cloud_suite.py --api ollama --base-url http://127.0.0.1:21434
.venv\Scripts\python.exe scripts\cloud\run_cloud_suite.py --api openai --base-url http://127.0.0.1:28080 --tests t0,t1,t2,t3
# 4) 取回服务器信息与日志(只含服务器侧元数据)
scp -r -i <key> -P <port> <user>@<host>:~/vi/results ./outputs/cloud-server-results
scp -r -i <key> -P <port> <user>@<host>:~/vi/logs ./outputs/cloud-server-logs
```

## 4b. 把远程 GPU 接到本机的产品命令(2026-10-04 起)

```powershell
# 启动隧道 + Ollama 协议翻译层(只监听 127.0.0.1;-Stop 只结束它自己启动的两个进程)
.\scripts\cloud\connect_remote.ps1 -HostName <host> -KeyPath $env:USERPROFILE\.ssh\vi_cloud
$env:VISUALINTEL_OLLAMA_URL = "http://127.0.0.1:21435"     # 只对当前这个 shell 生效
.\.venv\Scripts\python.exe -m visualintel scene <video> --at 100
Remove-Item Env:VISUALINTEL_OLLAMA_URL                      # 回到本机 Ollama
.\scripts\cloud\connect_remote.ps1 -Stop
# 本机 llama.cpp(核显)作对照,画面不出本机;-WithFacade 同时给它配 Ollama 协议翻译层(端口 21436):
.\scripts\cloud\start_local_llama.ps1 -WithFacade       # 用 $env:VISUALINTEL_OLLAMA_URL = "http://127.0.0.1:21436"
.\scripts\cloud\start_local_llama.ps1 -Stop
# 并排对比报告(远程模式只接受测试集里的公开/合成视频):
.\.venv\Scripts\python.exe scripts\cloud\compare_local_remote.py --video outputs\testkit-cloud\synthetic\moving-shapes.avi
```

**隐私:** 设置了 `VISUALINTEL_OLLAMA_URL` 之后,该 shell 里 `visualintel` 处理的画面(包括摄像头 demo 的画面)都会发往远程服务器。
没设置时行为与以前完全一样。摄像头或个人录像经远程测试之前,需要你明确同意。

## 5. 测什么(套件内容)

| 编号 | 内容 | 回答的问题 |
|---|---|---|
| t0 | 往返时延(20 次 GET)、已装模型清单、缺失模型自动跳过 | 隧道/网络底噪;模型是否到位 |
| t1 | 每个模型 × 最长边 640/448/320;每档 12 张**不同**新图 + 1 次丢弃的热身 + 重复图对照(缓存);记录墙钟、服务器端 prompt/生成耗时、`net_overhead_sec`(墙钟 − 服务器总耗时) | H1:GPU 上单次延迟;输入尺寸的影响;网络开销占比 |
| t2 | 并发 1/2/4/8(每档不同缩放边长以避免缓存命中),吞吐 rps、延迟中位/P95,配 `--price-per-hour` 得"每千次请求美元" | H2/H3:云端单位成本 vs 本地 |
| t3 | 合成圆图(1–6 个、已知颜色)的计数/颜色准确率,原图和 448 两档 | 缩小输入对精度的影响;模型间能力差 |
| t4 | 冷启动:先 `keep_alive: 0` 卸载再请求,记录 `load_duration`(仅 Ollama) | 按需启停的代价 |

输出:`outputs/cloud-run-<时间>-<api>/records.jsonl`(每次请求原始记录)与 `summary.json`。
COCO 图的场景描述在 `records.jsonl` 的 `response` 字段里,**质量评估由我自己逐条核对**,属于助手自评,
不是用户独立验收,会按此标注。

### 补充审计项(手动,按 AGENTS.md 第31条)

在实例上重启 llama-server 变更一个变量后重跑 `--api openai --tests t1`,逐项记录:`-ub`(256/512/1024/2048)、
`-fa`(开/关)、`--image-max-tokens`、Q4_K_M vs bf16(`WITH_BF16=1`)、`--parallel`(1/4/8)。
每项测完写入审计表的"已测范围 / 结果 / 是否穷尽"列;**没测的不写成"已最优"**。

## 6. 结束清单(最容易漏、最花钱)

1. 先确认结果已回传到本机(`outputs/cloud-run-*`、`outputs/cloud-server-*`)。
2. 关闭隧道;在实例上可执行 `bash ~/Visual_Intelligence_Integration/scripts/cloud/stop_servers.sh`(只停进程,**不停计费**)。
3. 在云平台控制台**终止(terminate)实例**,而不是只"停止":部分平台停止后仍收磁盘费。
4. 确认控制台显示当前每小时费用为 0;快照、持久卷、镜像也会计费,是否保留由用户决定。
5. 我不会替用户删除任何云端资源;我只会提醒。

## 7. 结果怎么用

- 把 t1/t2 的数值填入 `scripts/cost_model.py` 的 `PRICES`/实测延迟,重算"本地 vs 云端 vs 混合"的盈亏平衡;
- 回写 [cost-balance-target-2026-10-03.md](cost-balance-target-2026-10-03.md) 的 H1–H4 与决策框架;
- 回写 AGENTS 第31条审计表(模型、引擎、量化、并发行);
- 结论强度保持与证据匹配:一个实例、一次会话、n=12,只报描述统计,不做显著性声称。

## 8. 已知局限与未验证项

- ⚠ `setup_server.sh` 与 `stop_servers.sh` 没在真实服务器上运行过,可能因镜像差异(无 `zstd`、驱动版本、
  `tar --zstd`)首次失败;脚本对这些做了预检并在失败时给出提示,但不能保证。
- `response_format: json_schema` 写法已在本机 llama-server b11146(SYCL 版)上验证被接受;CUDA 版同一
  接口,但没在真实服务器上跑过。若被拒绝,套件会把 HTTP 错误记在 `records.jsonl` 并在 3 次连续失败后停止。
- 本机冒烟运行发现 Ollama 的 Vulkan 核显路径会产生非法输出(见延迟分布文档 §3.5);云端是 CUDA 路径,
  不一定有同样问题,所以 t1 的"合法 JSON 率"这一列在云上同样要看,不能只看耗时。
- 云端与本机用的不是同一个引擎栈(Ollama v0.35.1 对本机 0.34.4;llama.cpp CUDA 对 SYCL),
  所以"GPU 比核显快 N 倍"需要在同一引擎下比较,报告时必须注明。
- 平台带宽/出站流量费用、实例启动时间、Spot 被回收的概率未核实。
