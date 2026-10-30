---
name: BMJD 客户查岗平台
description: 客户查询、七层横向岗位对照与完整JD阅读的已实现视觉规范
colors:
  blue: "#3555d6"
  blue-soft: "#edf2ff"
  focus: "#1c3fbf"
  bg: "#f5f7fb"
  surface: "#fff"
  ink: "#22324b"
  muted: "#596980"
  line: "#dde4ef"
  blue-hover: "#2847c0"
  field-line: "#c6d0df"
  secondary-ink: "#415b87"
  secondary-line: "#c7d2e5"
typography:
  headline:
    fontFamily: '"Microsoft YaHei","PingFang SC",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif'
    fontSize: "27px"
    fontWeight: 650
    lineHeight: 1.5
    letterSpacing: "0.1px"
  title:
    fontFamily: '"Microsoft YaHei","PingFang SC",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif'
    fontSize: "16px"
    fontWeight: 650
    lineHeight: 1.6
  body:
    fontFamily: '"Microsoft YaHei","PingFang SC",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif'
    fontSize: "14px"
    lineHeight: 1.6
  label:
    fontFamily: '"Microsoft YaHei","PingFang SC",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif'
    fontSize: "12px"
    lineHeight: 1.6
  code:
    fontFamily: 'Consolas,"SFMono-Regular",monospace'
    fontSize: "11px"
    lineHeight: 1.6
    letterSpacing: "0.3px"
rounded:
  tag: "4px"
  compact: "5px"
  button: "6px"
  field: "7px"
  panel: "9px"
spacing:
  tight: "4px"
  small: "8px"
  medium: "12px"
  inset: "16px"
  section: "20px"
  roomy: "24px"
components:
  button-primary:
    backgroundColor: "{colors.blue}"
    textColor: "{colors.surface}"
    rounded: "{rounded.button}"
    padding: "10px 13px"
  button-primary-hover:
    backgroundColor: "{colors.blue-hover}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.secondary-ink}"
    rounded: "{rounded.button}"
    padding: "10px 13px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.field}"
    padding: "10px 11px"
  filter-chip:
    backgroundColor: "#f1f4fa"
    textColor: "#425a7c"
    rounded: "{rounded.tag}"
    padding: "3px 6px"
  results-panel:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.panel}"
  detail-drawer:
    backgroundColor: "{colors.surface}"
    padding: "20px 26px 28px"
    width: "min(470px,100vw)"
    height: "100dvh"
---

# Design System: BMJD 客户查岗平台

## Overview

**Creative North Star: "岗位横向层级对照"**

这是对已完成客户查询界面的扫描记录；上面的名称描述现有结构，不新增品牌隐喻。视觉以 BMJD 蓝色操作、白色阅读面、浅灰蓝工作区和紧凑中文信息组成。岗位方向、层级、代码和职责是主内容，操作用于定位、对比与带走结果。

适用范围仅为 `customer_portal/` 的模板、样式与查询交互，以及由它生成的 `BMJD客户查岗平台_20261030/BMJD客户查岗平台.html`。不适用于 `completion_tool/`、独立新增岗位工具或旧审议界面。新增入口指向同目录独立 HTML；此规范不要求这些工具换肤或改动业务逻辑。

提取依据是 `customer_portal/styles.css` 的最终级联、`template.html`、`portal-app.js` 与 `portal-core.js`。产品事实见 `PRODUCT.md`，本次页面方向见 `.impeccable/review/customer-brief.md`；本文不替代这两份文件。没有新增品牌字体、营销图或用户批准的视觉图片稿。

**Key Characteristics:**
- 桌面按职责系列为行，1—7层级为列；保留现有空位。
- 顶部查询与清单导航，左侧行业及职能筛选，主要宽度交给岗位结果。
- 手机默认列表，原生模态详情全屏阅读；可切换横向矩阵。
- 2—3岗并排展示完整JD，职责版本始终可辨。
- 离线单HTML使用本机系统字体与内联图标，不请求外部视觉资源。

## Colors

界面只有一组主要蓝色强调，辅以冷白、灰蓝分隔线和深蓝灰正文；不引入旧审议界面的琥珀、绿色状态语义。

### Primary
- **操作蓝**（`blue`）：主要按钮、当前导航、勾选控件、同方向当前层级和选中岗位边界。
- **浅蓝选择底**（`blue-soft`）：当前职能等轻量选中状态；其他矩阵匹配、上下文和当前岗位底色按现有组件分别保留，不能用单一底色抹平。
- **键盘焦点蓝**（`focus`）：交互控件的可见焦点轮廓。
- **按钮悬停蓝**（`blue-hover`）：主要按钮悬停。

### Neutral
- **工作区浅灰蓝**（`bg`）：页面底色。
- **阅读白**（`surface`）：顶栏、输入、结果、详情与对比列。
- **正文深蓝灰**（`ink`）：默认正文。
- **辅助蓝灰**（`muted`）：说明、统计和辅助标签。
- **分隔浅灰蓝**（`line`）：普通容器和内容分区边界。
- **输入描边**（`field-line`）：普通输入框、下拉框。
- **次操作文字与描边**（`secondary-ink`、`secondary-line`）：白底次按钮。

矩阵的蓝底配合匹配说明、当前边框和可读代码表达状态；空缺使用横线。错误提示沿用已有红色文字与浅红底，仅用于加载或操作失败。

**The Scope Rule.** 查询界面的蓝色表达交互和定位，不承载批准、审议或主库修改状态。

## Typography

**Body Font:** 中文优先的本机系统字体栈，见前置令牌；不加载网络字体。
**Label/Mono Font:** 岗位代码使用 Consolas、SFMono-Regular 与 monospace 回退；职责方向码段使用 Consolas 与 monospace。

字体以中文密集资料的可读性为主，没有独立展示字体。数字统计与代码使用等宽数字，代码完整显示；名称和长职责允许换行。

### Hierarchy
- **Headline**：页面主标题使用前置令牌；手机降为（23px）。
- **Title**：结果区标题使用前置令牌；手机为（15px）。详情标题在桌面为（24px / 1.55，650），中等屏为（21px），手机为（23px）。
- **Body**：普通正文使用前置令牌；完整JD采用（14px / 1.95），详情正文最大宽度（75ch）。
- **Label**：字段、说明、按钮附近信息围绕前置标签令牌；矩阵参考区间与岗位代码可小至（10px），不能据此缩小主要正文。
- **Code**：列表代码使用前置令牌；矩阵代码为（10px / 1.5），详情代码为（14px，600）。
- **Buttons**：标准按钮为（13px / 1.5，550）；紧凑分页、对比托盘和详情操作保留各自较小字号。

**The Code Identity Rule.** 名称可换行，代码保持完整；层级序号和参考职级区间不能代替岗位身份。

## Layout

主区域居中，最大宽度（1680px）；常规桌面内边距（29px 30px 20px）。顶栏高度（74px），含品牌、查询/清单导航与右侧独立新增入口。最终布局是两栏：筛选栏（210px）与可收缩结果栏，间距（20px）；不要恢复样式文件较早定义的三栏常驻详情布局。

宽屏（≥1600px）筛选栏为（220px）；≤1150px 时为（188px），栏间距（14px）；≤960px 时为（178px）。≤640px 改为单列，主区域内边距（22px 16px 18px），顶栏高度（66px）。筛选默认收起，通过“筛选条件”按钮展开，职能按钮改为两列。

桌面默认矩阵，手机首次打开默认列表；视图可以手动切换，初始选择由加载时视口决定。矩阵每行对应现有职责系列，职责方向列常规宽度（156px），≤1150px 为（142px）；七个层级列始终保留。矩阵最小宽度常规为（1000px），≤1150px 为（980px），局部横向滚动。表头与左侧职责方向列固定。滚动区最大高度常规为（650px），≤960px 为（620px），手机为（600px）。手机列表不限制内部高度。

矩阵搜索突出命中的岗位，并保留同系列邻级作为上下文；所有上下文仍限定在所选行业。点击表头切换层级定位。空位显示横线，不能补造岗位、按相似名称合并系列，或把参考职级区间变成评价分数。

桌面详情为右侧原生模态抽屉，宽度（min(470px,100vw)）、高度（100dvh），内容独立滚动。手机≤640px 为全屏原生模态详情。对比区桌面按当前选择数等宽并排，保持完整职责；手机为横向滚动，每列占容器（86%），带邻近滚动吸附。

## Elevation & Depth

普通筛选、结果、清单与对比容器通过白底、细线与轻色分区表达层次。搜索与固定方向列有很轻的局部阴影；主要覆盖层是详情抽屉和短暂提示。矩阵当前岗位使用内描边式阴影，属于选中状态而非悬浮卡片。

### Shadow Vocabulary
- **搜索轻阴影**（`0 3px 9px #243a6505`）：搜索栏；焦点时改为蓝色（`0 0 0 1px var(--blue)`）。
- **方向列边缘**（`3px 0 5px #25416505`）：横向滚动时标识固定列边界。
- **详情覆盖层**（`-12px 0 38px #1d35582e`）：右侧抽屉；背景遮罩（`#172f501c`）。
- **操作提示**（`0 9px 26px #233a6028`）：底部 toast。
- **选中岗位**（`inset 0 0 0 2px var(--blue)`）：当前岗位单元格；表头定位另用底边内阴影（`inset 0 -3px 0 #3555d6`）。

**The Reading Surface Rule.** 日常数据阅读面使用细线分区；保留已有局部阴影和模态层，不为每个岗位增加浮起效果。

## Shapes

现有轮廓是轻圆角控件与直角数据网格。标签用前置 `tag` 圆角；职能按钮、关闭按钮和层级切换用 `compact`；标准按钮和视图切换用 `button`；字段用 `field`；大阅读容器与搜索框用 `panel`。不将它们统一改成胶囊或夸张圆角。

矩阵单元格、岗位选择按钮和原生详情抽屉保持直角。边框通常（1px），详情左边界独立描边。图标是内联线条SVG，通常（20px）与（1.7）描边，辅助关闭和外链图标按现有尺寸缩小。

## Components

### Buttons

主要操作明确、常规操作轻量。标准按钮使用前置圆角和内边距，最小高度（41px）；蓝底白字用于加入清单、导出与开始对比。次按钮白底描边，悬停转浅蓝底并加深边框；文字按钮承担重置、返回、复制代码与清空。

控件可见焦点为（3px）轮廓、外偏移（3px）；搜索输入由容器的 focus-within 提供焦点。禁用按钮保留（.45）不透明度与不可用光标。导航、岗位选择、职能按钮和标准按钮使用背景、文字、边框色的（.16s ease）过渡。

### Inputs / Fields

普通输入与下拉框白底细线，最小高度（43px）；筛选栏字段桌面为（39px）并使用（12px）字号。手机筛选字段和主搜索输入使用（16px）字号。主搜索是较大的白色容器，桌面最小高度（55px），有搜索图标和斜杠快捷键提示；手机为（49px），隐藏快捷键提示。范围下拉框默认“名称 / 代码”，可切换“同时搜索职责”。

### Navigation

白色横向顶栏，当前页面以操作蓝文字和（2px）底线表达。清单导航带计数。桌面品牌显示 BMJD 与“岗位字典”，手机隐藏副标题并缩小标记。新增岗位入口保持独立外链图标与新窗口行为。

### Chips

活动筛选标签为静态浅灰蓝标签，允许长文本换行。对比托盘中的岗位标签是可移除按钮，保留文字与关闭符号。行业标签说明岗位适用范围；不复用为审议状态。

### Cards / Containers

筛选与结果是细边框白面板。筛选内边距（19px 15px），桌面吸顶（18px）并可在视口内滚动；结果标题区常规内边距（18px 19px 13px）。岗位列表以分隔线组织，每行可打开详情，并单独提供对比复选框。

### Seven-Level Matrix

每个已存在岗位单元格显示名称、等宽代码和独立对比复选框；点击名称打开详情。表头显示层级名称、序号和参考职级区间，点击后再次点击可取消定位。当前岗位的内描边、搜索匹配浅蓝底、同系列上下文弱化字色分别保留。空位不能表现为可新增或可编辑控件。

### Native Detail Dialog

详情使用原生 `dialog.showModal()`，打开后聚焦岗位标题；关闭后尽可能回到来源岗位按钮。保留返回与关闭操作、原生 Escape 关闭和焦点约束。内容依次为代码、名称、系列/层级、行业、同方向层级、职责版本、完整职责和操作。

同方向层级按钮只显示实际存在的岗位，并按当前职责行业限制范围。职责版本可切换全局通用与适用行业；行业没有专业稿时明确说明沿用通用职责。清单与对比均保存所选职责版本；切换后已有记录可更新。

### Full JD Comparison and Saved List

对比托盘最多（3）岗，少于（2）岗时禁用开始对比；各列完整展示名称、代码、层级、职能/系列、职责版本和全部职责，不以摘要替代。允许复制对比内容与打开单岗详情。

清单保存于当前浏览器，支持移除、查看和CSV导出；存储不可用时明确提示仅本次页面保留。这里不表达同步、编辑主库或审核流程。

加载使用轻色进度条（1.3s ease-in-out infinite alternate），失败提供重新载入。toast 是短暂操作反馈，空结果提供清除条件。`prefers-reduced-motion:reduce` 时关闭动画与过渡并取消平滑滚动。

## Do's and Don'ts

### Do:
- **Do** 将这份规范限定为客户查询界面，沿用蓝白操作与中文系统字体。
- **Do** 保留七列层级、职责方向固定列、可切换列表和手机全屏原生详情。
- **Do** 完整显示岗位代码、职责版本与长JD，2—3岗对比保留全部职责。
- **Do** 将匹配岗位与邻级上下文区分，并让两者都遵守行业范围。
- **Do** 保留键盘焦点、原生模态行为、禁用、空态、错误和本机存储提示。
- **Do** 保持新增入口独立，让客户查询的岗位名称、代码和JD只读。

### Don't:
- **Don't** 将客户查询规范应用到旧 `completion_tool/`，或据旧审议 sidecar 重写客户界面。
- **Don't** 添加营销图、外部字体、新品牌设定或审议/批准状态体系。
- **Don't** 按名称相似合并系列、补造七级空位，或把参考职级区间当作自动评价规则。
- **Don't** 恢复三栏常驻详情布局，或在手机强制以矩阵作为初始视图。
- **Don't** 截断完整JD、以摘要替代对比内容，或省略职责行业版本。
- **Don't** 将本机清单、复制或导出描述成主库修改、多人同步或自动回写。
