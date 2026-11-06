import { useEffect, useRef, useState } from "react";
import {
  FOLLOW_SYSTEM,
  getSelectedMic,
  listMicDevices,
  openMic,
  setSelectedMic,
} from "../lib/mic";
import type { MicDevice } from "../lib/mic";

/**
 * 麦克风选择：默认跟随系统，可手动指定某个输入设备。
 *
 * 为什么单独做成一个区块：用户机器上常装 Voicemeeter、NVIDIA Broadcast 等
 * 虚拟音频设备，浏览器默认可能选中它们导致录到静音，表现为「没有识别到内容」。
 * 这里除了下拉框，还提供实时电平条——选完立刻能确认这个设备到底能不能录到声音。
 */
export default function MicSettingsCard() {
  const [devices, setDevices] = useState<MicDevice[]>([]);
  const [selected, setSelected] = useState<string>(() => getSelectedMic());
  const [level, setLevel] = useState(0);
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState("");
  const [peak, setPeak] = useState(0);
  const stopRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    // 首次挂载时读取设备：用保存的值而不是闭包里的 selected，
    // 避免把 refresh 列为依赖后每次选择设备都重新挂载。
    void (async () => {
      try {
        const probe = await openMic(getSelectedMic());
        probe.getTracks().forEach((track) => track.stop());
        setDevices(await listMicDevices());
      } catch (event) {
        setError((event as Error).message || "读取麦克风列表失败");
      }
    })();
    return () => stopRef.current?.();
  }, []);

  async function refresh() {
    setError("");
    try {
      // 先取得一次麦克风权限，否则浏览器不显示设备名
      const probe = await openMic(selected);
      probe.getTracks().forEach((track) => track.stop());
      setDevices(await listMicDevices());
    } catch (event) {
      setError((event as Error).message || "读取麦克风列表失败");
    }
  }

  function stopTest() {
    stopRef.current?.();
    stopRef.current = null;
    setTesting(false);
    setLevel(0);
  }

  async function startTest() {
    stopTest();
    setError("");
    setPeak(0);
    try {
      const stream = await openMic(selected);
      const context = new AudioContext();
      const analyser = context.createAnalyser();
      analyser.fftSize = 1024;
      context.createMediaStreamSource(stream).connect(analyser);
      const buffer = new Uint8Array(analyser.fftSize);
      setTesting(true);
      let maxPeak = 0;
      const timer = window.setInterval(() => {
        analyser.getByteTimeDomainData(buffer);
        let localPeak = 0;
        for (const value of buffer) {
          localPeak = Math.max(localPeak, Math.abs(value - 128));
        }
        maxPeak = Math.max(maxPeak, localPeak);
        setLevel(Math.min(1, localPeak / 64));
        setPeak(maxPeak);
      }, 100);
      stopRef.current = () => {
        window.clearInterval(timer);
        stream.getTracks().forEach((track) => track.stop());
        void context.close().catch(() => undefined);
      };
    } catch (event) {
      // 试音必须暴露真实结果：选中的设备打不开就直说，不要偷偷换成别的
      setError(`这个设备打不开：${(event as Error).message || "未知原因"}`);
      setTesting(false);
    }
  }

  function choose(deviceId: string) {
    stopTest();
    setSelected(deviceId);
    setSelectedMic(deviceId);
  }

  return (
    <div className="card" style={{ marginTop: 12 }}>
      <h2>麦克风</h2>
      <p className="muted">
        默认跟随系统输入设备。如果说话后提示「没有识别到内容」，多半是选中了虚拟音频设备
        （例如 Voicemeeter、NVIDIA Broadcast），换一个真实麦克风即可。
      </p>

      {error && <div className="alert">{error}</div>}

      <div className="field-grid">
        <div>
          <label htmlFor="mic-device">输入设备</label>
          <select
            id="mic-device"
            value={selected}
            onChange={(event) => choose(event.target.value)}
          >
            <option value={FOLLOW_SYSTEM}>跟随系统默认</option>
            {devices.map((device) => (
              <option key={device.deviceId} value={device.deviceId}>
                {device.label}
              </option>
            ))}
            {/* 保存的设备已拔掉时，补一个占位项，避免下拉框显示空白 */}
            {selected !== FOLLOW_SYSTEM && !devices.some((d) => d.deviceId === selected) && (
              <option value={selected}>已保存的设备（当前不可用）</option>
            )}
          </select>
        </div>
      </div>

      <div className="row" style={{ gap: 8, alignItems: "center", marginTop: 8 }}>
        <button type="button" className="ghost" onClick={testing ? stopTest : () => void startTest()}>
          {testing ? "停止试音" : "试音：看看能不能录到"}
        </button>
        <button type="button" className="ghost" onClick={() => void refresh()}>
          刷新设备列表
        </button>
      </div>

      {testing && (
        <div style={{ marginTop: 10 }}>
          <div className="voice-meter">
            <div className="voice-meter-fill" style={{ width: `${Math.round(level * 100)}%` }} />
          </div>
          <p className="muted" style={{ marginTop: 6 }}>
            {peak < 3
              ? "几乎没声音：这个设备可能录不到，换一个试试"
              : peak < 15
                ? "声音很弱：正常说话应该更高，检查系统输入音量"
                : "能录到声音，这个设备可用"}
            {`（峰值 ${peak}/128）`}
          </p>
        </div>
      )}
    </div>
  );
}
