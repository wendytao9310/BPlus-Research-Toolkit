# NVC Analysis Preparation

每位被试按原始模态、行为、sync 与 derivatives 分层保存。所有信号保留原采样率、设备时钟和事件；派生数据记录处理版本。EEG 提取 ERP/频带/包络，fNIRS 提取 HbO/HbR/HbT/HRF，以共同事件和验证后的时钟映射对齐。

推荐向 EEG-BIDS、NIRS-BIDS/SNIRF 和 events.tsv 靠拢，但原始厂商文件只读保留。NVC 的 lag、互相关、替代检验和 bootstrap 实现位于 `src/bplus/nvc.py`；合成验证不能替代真实设备验证。

