# 环境概况测试（2026-09-30）

用户明确当前优先目标：理解大致环境、主要人物与显眼物体，不要求识别
杯中内容等隐藏细节。导航、安全建议暂不作为该目标的质量验收条件。

新增 `scene VIDEO [--at SECONDS]`，默认取视频中间一帧，仅输出一两句
环境概况。保留原有 report/ask 行为。单帧不能代表整个视频，也不能用来
验证动作时间线或确保捕捉到短暂事件。

## 图片来源与核对标准

通过 Google 图片搜索 `wikimedia commons street kitchen park` 选择以下
三张公开图，再从 Wikimedia Commons 下载原图。仅图片送入本地模型，
不发送文件名、网页标题、地点描述或人工核对结论。

| 图片 | 作者、许可 | 助手看图后的概况参照 |
|---|---|---|
| [Restaurants in the park](https://commons.wikimedia.org/wiki/File:Restaurants_in_the_park.jpg) | Souka Kinmei；[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | 户外店铺/餐饮区、人群、树木、建筑与铺装步道 |
| [Kitchen impromptu street](https://commons.wikimedia.org/wiki/File:Kitchen_impromptu_street.jpg) | Wilfredor；[CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/) | 街边烹饪摊、人物、遮棚/伞、锅盆、车辆 |
| [Cherry Street Park](https://commons.wikimedia.org/wiki/File:Cherry_Street_Park_(Hong_Kong).jpg) | Mk2010；[CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/) | 公园入口、树木、人、步道、围栏及背景楼宇 |

参照由助手视觉检查产生，未经独立人工验收。目标是环境类别与主要内容
是否吻合，不考核地点名称、商标、饮品、身份或精确物体计数。

## 原图实测

MiniCPM-V 4.6，Ollama 0.34.4；temperature=0、seed=42、num_predict=96；
单图片、串行、JSON answer 字段，生产验证与一次修复重试策略。三次均一次
通过，没有重试。图片原尺寸依次为 3200×1800、4288×2848、3508×2630。

| 图片 | 模型原文 | 端到端秒数 | 质量判断 |
|---|---|---:|---|
| 户外餐饮区 | A bustling outdoor area with people near shops, featuring trees and clear skies, main focus on human activity and visible store fronts.) | 39.97 | 符合概况目标；未进一步识别餐饮，尾部有多余括号 |
| 街边烹饪摊 | A bustling market scene with people preparing food under umbrellas and near vehicles. | 42.18 | 符合概况目标 |
| 公园入口 | The image shows a park entrance with people walking, surrounded by trees and buildings in the background.) | 47.63 | 环境与主要物体吻合；静态图中“walking”是姿态推断，尾部有多余括号 |

前两次 Ollama prompt_eval_duration 分别为 35.78、38.44 秒，eval_duration
分别为 1.57、0.71 秒。这里输入处理包含视觉处理等工作，不能单凭这个指标
把全部耗时归于某个独立组件。`/api/ps` 报告模型 size_vram=0。
这些单次结果表明文字输出不是主要耗时，尚未满足低延迟目标。

测试来源、原图 SHA256、请求参数、原始响应、重试次数及耗时保存在
`outputs/google-scene-evaluation-20260930/`，不纳入 Git。

## 先前视频单帧验证

既有测试视频 0 秒与 8 秒的 scene 请求分别为 26.14 与 37.47 秒，
输出人物/房间/货架及人物持杯。相比旧多帧任务不是相同语义工作量，
也没有控制缓存与负载，不能宣称稳定的加速比例。

## 640 像素对照结果

按比例缩小到最长边 640，不裁剪，JPEG 重新编码；原图全部保留。
模型、prompt、schema 与采样参数相同，三次均一次通过，无修复重试。

| 图片 | 原图秒数 | 缩小后秒数 | 缩小后的原文 |
|---|---:|---:|---|
| 户外餐饮区 | 39.97 | 16.81 | A bustling outdoor area with people near shops, trees, and clear skies, focusing on human activity and visible structures.) |
| 街边烹饪摊 | 42.18 | 17.80 | A bustling market scene with people preparing food under canopies, surrounded by visible cooking equipment and vehicles. |
| 公园入口 | 47.63 | 17.81 | The image shows a park entrance with people nearby, surrounded by greenery and buildings in the background.) |

助手核对：三张的环境类别与主要内容均保留。结果支持继续采用低分辨率
进行概况任务实验；还未证明更细小物体、复杂场景或视频时序的效果。
原图组先测、缩小组后测，每图每尺寸只有一次；没有随机顺序或稳态重复，
不能把本轮下降量推广为稳定加速比例。缩小组图片编码与 SHA256 都不同，
但后端缓存实现的影响未单独隔离。16–18 秒仍不算实时环境感知。

原始缩小组记录位于 `outputs/google-scene-evaluation-20260930/resized-640/`。

## 复现命令

```powershell
.venv\Scripts\python scripts/evaluate_scenes.py image1.jpg image2.jpg image3.jpg --output outputs/new-scene-run
.venv\Scripts\python scripts/evaluate_scenes.py image1.jpg image2.jpg image3.jpg --max-image-side 640 --output outputs/new-scene-640-run
```

输出目录必须不存在，保存全部原始调用响应。缩小图片是评估选项，
未自动改变生产模式的默认输入分辨率。顺序测试可能受模型加载、缓存和
机器负载影响；不同图/图尺寸的单次耗时不是稳定性能基准。
