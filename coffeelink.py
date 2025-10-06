# ==============================================================================
# --- ライブラリのインポート ---
# ==============================================================================
import time
import numpy as np
import sys
import warnings
import os
import csv
import tkinter as tk
import io
import threading

# from scipy.signalのlfilterは音声処理にしか使われていないため、実質的に不要になります
from scipy.signal import butter, filtfilt, find_peaks

# --- 生体信号処理ライブラリ ---
from bitalino import BITalino
import neurokit2 as nk
from neurokit2.misc import NeuroKitWarning
from gpiozero import PWMOutputDevice, DigitalOutputDevice, Button
from PIL import Image, ImageDraw, ImageFont, ImageTk
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse


# ==============================================================================
# --- 全体の設定項目 ---
# ==============================================================================
warnings.filterwarnings("ignore", category=NeuroKitWarning)
execution_timestamp = time.strftime("%Y%m%d_%H%M%S")
CSV_SAVE_DIRECTORY = "/home/exopia/my_project/last_result_csv"
IMG_SAVE_DIRECTORY = "/home/exopia/my_project/last_result_pic"

# ==============================================================================
# --- 抽出パラメータ設定 ---
# ==============================================================================

# --- 抽出の中心となるバルブ開放時間(mid)を設定してください ---
# lowとhighは high = 2 * low, mid = (low + high) / 2 の関係に基づき自動計算されます
VALVE_TIME_MID = 12.0

# --- 上記設定に基づき、lowとhighを自動計算 ---
_valve_time_low = (2/3) * VALVE_TIME_MID
_valve_time_high = (4/3) * VALVE_TIME_MID

VALVE_TIME = {
    'low': _valve_time_low,
    'mid': VALVE_TIME_MID,
    'high': _valve_time_high
}

# --- 各バルブ開放時間に対応するパラメータ ---
TIME_TO_GRAMS = {
    'low': 40,
    'mid': 60,
    'high': 80
}

MOTOR_SPEED = {
    'low': 0.12,
    'mid': 0.10,
    'high': 0.08
}

# --- 抽出インターバル時間 ---
INTERVAL_TIME = {
    'low': 30,
    'mid': 45,
    'high': 60
}

# --- 各投下のリラックス度スコアの閾値 ---
THRESHOLDS = {
    'pour_1':          {'low': 30.0, 'high': 70.0},  # 1投目の味（sweet/basic/fruity）を決める閾値
    'pour_2_interval': {'low': 30.0, 'high': 70.0},  # 2投目の後のインターバルを決める閾値
    'pour_3':          {'low': 45.0, 'high': 55.0},  # 3投目の濃度（strong/medium/mild）を決める閾値
    'pour_4':          {'low': 45.0, 'high': 55.0}   # 4投目の濃度（thick/thin）を決める閾値
}

# 生体信号の妥当性評価範囲
PLAUSIBLE_RANGES = {
    'bpm': (40, 180),   # 心拍数の妥当な範囲 (BPM)
    'rri': (333, 1500), # R-R間隔の妥当な範囲 (ms)。BPM換算で 40BPM ~ 180BPM に相当
}


# --- 生体信号(BITalino) 設定 ---
macAddress = "98:D3:11:FD:FD:B5"
samplingRate = 100
nSamples = 100
acqChannels = [0, 1]
RELAXATION_SCORE_WEIGHTS = {'area': 0.50, 'scl': 0.30, 'scr_count': 0.10, 'scr_amp': 0.10}

# --- モーター & GPIO 設定 ---
ENA, IN1, IN2, EMERGENCY_STOP_BUTTON_PIN = 18, 23, 24, 2
IN3, IN4 = 17, 27
BASE_MIN_SPEED, BASE_ACCEL_STEPS, BASE_ACCEL_INTERVAL, BASE_FREQUENCY = 0.12, 20, 0.05, 100
BASE_DECEL_STEPS, BASE_DECEL_INTERVAL = 20, 0.05
emergency_stop_triggered = False

# ==============================================================================
# --- Tkinter ウィンドウとフォントの初期化 ---
# ==============================================================================
root = tk.Tk()
root.title("Biofeedback リアルタイムレポート (Z-score model)")
root.geometry("1800x800")
root.configure(bg='white')
canvas_label = tk.Label(root, bg='white')
canvas_label.pack(fill="both", expand=True)
FONT_PATH = ""
try:
    font_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
    FONT_PATH = os.path.join(font_dir, "NotoSansCJKjp-Regular.otf")
    fonts = (ImageFont.truetype(FONT_PATH, 48),
             ImageFont.truetype(FONT_PATH, 32),
             ImageFont.truetype(FONT_PATH, 42),
             ImageFont.truetype(FONT_PATH, 28),
             ImageFont.truetype(FONT_PATH, 20),
             ImageFont.truetype(FONT_PATH, 40),
             ImageFont.truetype(FONT_PATH, 60)) # 結果コード用のフォント
    plt.rcParams['font.family'] = 'sans-serif'
    plt.rcParams['font.sans-serif'] = ['Noto Sans CJK JP', 'DejaVu Sans']
except Exception as e:
    print(f"❌ フォント読み込み失敗: {e} デフォルトフォントを使用します。")
    fonts = tuple(ImageFont.load_default() for _ in range(7))

# ==============================================================================
# --- 関数定義 ---
# ==============================================================================

# --- GUI・ロジック関連のヘルパー関数 ---
def get_status_from_score(score):
    if score >= 85:   return "最大リラックス", "#1dd1a1"
    elif score >= 75: return "すごくリラックス", "#10ac84"
    elif score >= 65: return "リラックス",       "#7bed9f"
    elif score >= 55: return "少しリラックス",   "#a29bfe"
    elif score >= 45: return "普通",           "#54a0ff"
    elif score >= 35: return "すこし興奮状態",   "#feca57"
    elif score >= 25: return "興奮状態",       "#ff9f43"
    elif score >= 15: return "すごく興奮状態",   "#ff6b6b"
    else:             return "最大興奮状態",     "#ee5253"

def emergency_stop():
    global emergency_stop_triggered
    if not emergency_stop_triggered:
        print("\n!!! 緊急停止ボタンが押されました !!!")
        emergency_stop_triggered = True

def create_report_image(current_row, history, fonts, extraction_start_time):
    font_header, font_metric_label, font_metric_value, font_time_label, font_graph, font_status, font_result_code = fonts
    img = Image.new("RGBA", (1800, 800), "white"); draw = ImageDraw.Draw(img)
    
    label = current_row.get('interval_label', '')
    draw.text((50, 20), f"区間: {label}", font=font_header, fill="black")
    
    if label in ["計測開始待機中..."]:
        status_text, status_color = "測定中", "#808e9b"
    else:
        score = current_row.get('relaxation_score', 0)
        status_text, status_color = get_status_from_score(score)
    
    draw.text((1250, 20), f"現在の状態: {status_text}", font=font_status, fill=status_color)
    draw.line([(50, 90), (1750, 90)], fill="#dfe4ea", width=4)

    bio_metrics = [("心拍数", f"{current_row.get('mean_hr', 0):.1f} BPM"), ("SCL平均", f"{current_row.get('mean_scl', 0):.2f} µS"), ("SCRピーク数/分", f"{current_row.get('scr_ppm', 0):.1f} 回/分"), ("Lorenz面積", f"{current_row.get('lorenz_area', 0):.0f}")]
    for i, (label, value) in enumerate(bio_metrics):
        y_pos = 125 + i * 80
        draw.text((70, y_pos), label, font=font_metric_label, fill="gray"); draw.text((380, y_pos - 5), value, font=font_metric_value, fill="black", anchor="lt")

    lorenz_plot_area = (70, 460, 520, 780)
    draw.rectangle(lorenz_plot_area, outline="#ced6e0", width=2)
    lorenz_img = current_row.get('lorenz_plot_image')
    if lorenz_img:
        lorenz_img.thumbnail((lorenz_plot_area[2]-lorenz_plot_area[0]-10, lorenz_plot_area[3]-lorenz_plot_area[1]-10))
        img.paste(lorenz_img, (lorenz_plot_area[0]+5, lorenz_plot_area[1]+5))
    else: draw.text((295, 620), "待機中...", font=font_metric_label, fill="gray", anchor="mm")
    
    log_title_pos = (600, 125)
    draw.text(log_title_pos, "抽出メソッドログ", font=font_metric_label, fill="black")
    
    method_log = {}
    for row in history:
        label = row.get('interval_label')
        method = row.get('method_text')
        if label and method and ('投目' in label or '追加' in label):
                method_log[label] = method

    y_pos_log = 185
    for i in range(1, 3):
        label_text = f"{i}投目"
        method = method_log.get(label_text, "---")
        draw.text((log_title_pos[0], y_pos_log), f"{label_text}[味]:", font=font_metric_label, fill="gray")
        draw.text((log_title_pos[0] + 220, y_pos_log - 5), method, font=font_metric_value, fill="#c0392b", anchor="lt")
        y_pos_log += 60
    for i in range(3, 5):
        label_text = f"{i}投目"
        method = method_log.get(label_text, "---")
        draw.text((log_title_pos[0], y_pos_log), f"{label_text}[濃度]:", font=font_metric_label, fill="gray")
        draw.text((log_title_pos[0] + 220, y_pos_log - 5), method, font=font_metric_value, fill="#c0392b", anchor="lt")
        y_pos_log += 60
    if "追加" in method_log:
        draw.text((log_title_pos[0], y_pos_log), "追加[濃度]:", font=font_metric_label, fill="gray")
        draw.text((log_title_pos[0] + 220, y_pos_log - 5), method_log["追加"], font=font_metric_value, fill="#c0392b", anchor="lt")

    # 結果コードの描画
    result_code = current_row.get('result_code')
    if result_code:
        draw.text((log_title_pos[0], y_pos_log + 10), "最終結果コード:", font=font_metric_label, fill="black")
        draw.text((log_title_pos[0] + 300, y_pos_log + 5), result_code, font=font_result_code, fill="#2c3e50", anchor="lt")

    recipe_title_pos_y = y_pos_log + 120 # 結果コード表示エリアを確保
    draw.text((log_title_pos[0], recipe_title_pos_y), "抽出レシピ", font=font_metric_label, fill="black")
    
    recipe_plan = current_row.get('recipe_plan', [])
    y_pos_recipe = recipe_title_pos_y + 50
    for line in recipe_plan:
        draw.text((log_title_pos[0], y_pos_recipe), line, font=font_graph, fill="black", anchor="lt")
        y_pos_recipe += 35
    
    gx, gy, gw, gh = 1150, 120, 580, 580
    draw.rectangle([(gx, gy), (gx + gw, gy + gh)], outline="#ced6e0", width=4)
    draw.text((gx + gw/2, gy - 30), "リラックス度スコア推移", font=font_header, fill="black", anchor="mt")
    draw.line([(gx, gy + gh/2), (gx + gw, gy + gh/2)], fill="#a4b0be", width=2); draw.text((gx - 15, gy+gh/2), "50", font=font_graph, fill="#a4b0be", anchor="rm")
    
    scores = [row['relaxation_score'] for row in history if 'relaxation_score' in row and isinstance(row.get('relaxation_score'), (int, float))]
    if len(scores) > 1:
        points = [(gx + (i / (len(history) - 1)) * gw, gy + gh - (s / 100.0) * gh) for i, s in enumerate(scores)]
        draw.line(points, fill="#54a0ff", width=5)
        for p in points: draw.ellipse([(p[0]-7, p[1]-7), (p[0]+7, p[1]+7)], fill="#54a0ff", outline="white", width=2)
    
    return img

def create_lorenz_plot_image(rri_data, interval_label):
    # 計算前に rri_data をリストからNumPy配列に変換する
    rri_data = np.array(rri_data)

    if len(rri_data) < 2: return None, np.nan
    
    x_axis, y_axis = rri_data[:-1], rri_data[1:]
    sd1 = np.sqrt(0.5 * np.std(y_axis - x_axis) ** 2)
    sd2 = np.sqrt(0.5 * np.std(y_axis + x_axis) ** 2)
    lorenz_area = np.pi * sd1 * sd2
    
    fig, ax = plt.subplots(figsize=(4.5, 4.5), dpi=90)
    ax.scatter(x_axis, y_axis, alpha=0.6, edgecolors='k', s=20)
    ax.set_title("Lorenz Plot", fontsize=14)
    ax.set_xlabel("RRI_i (ms)", fontsize=10)
    ax.set_ylabel("RRI_{i+1} (ms)", fontsize=10)
    ax.grid(True, linestyle='--', alpha=0.6)
    
    center = (np.mean(x_axis), np.mean(y_axis))
    ellipse = Ellipse(xy=center, width=2*sd2, height=2*sd1, angle=45, edgecolor='r', fc='None', lw=2, linestyle='--')
    ax.add_patch(ellipse)
    
    min_val, max_val = min(rri_data) - 50, max(rri_data) + 50
    ax.set_xlim(min_val, max_val)
    ax.set_ylim(min_val, max_val)
    ax.set_aspect('equal', adjustable='box')
    
    plt.tight_layout(pad=0.5)
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    plt.close(fig)
    buf.seek(0)
    
    return Image.open(buf), lorenz_area

def update_display(current_row, history, fonts, extraction_start_time):
    img = create_report_image(current_row, history, fonts, extraction_start_time)
    photo = ImageTk.PhotoImage(img)
    canvas_label.config(image=photo); canvas_label.image = photo
    root.update()
    return img

def motor_thread_task(max_speed, steady_time, ena, in1, in2, solenoid_in3, solenoid_in4):
    global emergency_stop_triggered
    valve_timer = None
    def close_valve():
        solenoid_in3.off()
        print(f"タイマーによりバルブ閉鎖 (設定時間: {steady_time:.1f}秒)")
    try:
        print("電磁バルブ ON (スレッド)"); solenoid_in3.on(); solenoid_in4.off()
        valve_timer = threading.Timer(steady_time, close_valve)
        valve_timer.start()
        time.sleep(1)
        if emergency_stop_triggered: raise InterruptedError
        print("モーター起動 (スレッド)"); in1.on(); in2.off()
        min_speed = min(BASE_MIN_SPEED, max_speed); speed_range = max_speed - min_speed
        print("モーター加速 (スレッド)");
        for i in range(BASE_ACCEL_STEPS + 1):
            if emergency_stop_triggered: raise InterruptedError
            ena.value = min_speed + ((i / BASE_ACCEL_STEPS) * speed_range); time.sleep(BASE_ACCEL_INTERVAL)
        print("定速維持 (スレッド)"); end_time = time.time() + steady_time
        while time.time() < end_time:
            if emergency_stop_triggered: raise InterruptedError
            time.sleep(0.01)
        print("モーター減速 (スレッド)")
        for i in range(BASE_DECEL_STEPS, -1, -1):
            if emergency_stop_triggered: raise InterruptedError
            ena.value = min_speed + ((i / BASE_DECEL_STEPS) * speed_range); time.sleep(BASE_DECEL_INTERVAL)
        print("モーター動作完了 (スレッド)")
    except InterruptedError:
        print("シーケンスが中断されました (スレッド)。")
    finally:
        if valve_timer and valve_timer.is_alive(): valve_timer.cancel()
        print("GPIOリソースを解放 (スレッド)"); ena.off(); in1.off(); solenoid_in3.off()
        ena.close(); in1.close(); in2.close(); solenoid_in3.close(); solenoid_in4.close()

def start_motor_and_valve_sequence(max_speed, steady_time):
    print(f"\n--- モーター&バルブ シーケンス開始 (max={max_speed:.2f}, time={steady_time:.1f}s) ---")
    ena_pin = PWMOutputDevice(ENA, frequency=BASE_FREQUENCY); in1_pin = DigitalOutputDevice(IN1); in2_pin = DigitalOutputDevice(IN2)
    solenoid_in3 = DigitalOutputDevice(IN3); solenoid_in4 = DigitalOutputDevice(IN4)
    valve_start_time = time.time()
    motor_thread = threading.Thread(target=motor_thread_task, args=(max_speed, steady_time, ena_pin, in1_pin, in2_pin, solenoid_in3, solenoid_in4))
    motor_thread.start()
    return steady_time, valve_start_time, motor_thread

def analyze_interval_data(ecg_data, eda_data, sr, interval_label):
    results = {'mean_hr':np.nan,'rmssd':np.nan,'hf_power':np.nan,'lf_hf_ratio':np.nan, 'mean_scl':np.nan,'scr_count':np.nan, 'scr_ppm':np.nan, 'scr_amplitude_mean': np.nan, 'lorenz_plot_image': None, 'lorenz_area': np.nan}
    if len(ecg_data) < sr: return results

    duration_sec = len(ecg_data) / sr

    try:
        # --- ECG/HRV 解析 (外れ値処理あり) ---
        nyquist = 0.5*sr; low, high = 5/nyquist, 15/nyquist
        if high >= 1: high = 0.99
        filtered_ecg = filtfilt(*butter(2, [low, high], 'band'), ecg_data)
        peaks, _ = find_peaks(filtered_ecg, height=0.6*np.max(filtered_ecg), distance=sr*0.4)
        
        if len(peaks) > 1:
            rri_ms = (np.diff(peaks) / sr) * 1000
            
            min_rri, max_rri = PLAUSIBLE_RANGES['rri']
            rri_filtered = [r for r in rri_ms if min_rri <= r <= max_rri]
            
            if len(rri_filtered) > 1:
                results['mean_hr'] = 60000 / np.mean(rri_filtered)
                lorenz_img, lorenz_area = create_lorenz_plot_image(rri_filtered, interval_label)
                results['lorenz_plot_image'] = lorenz_img
                results['lorenz_area'] = lorenz_area
            
                if len(peaks) > 20:
                    hrv_t = nk.hrv_time(peaks, sampling_rate=sr, show=False); results['rmssd'] = hrv_t.get('HRV_RMSSD', [np.nan]).iloc[0]
                    hrv_f = nk.hrv_frequency(peaks, sampling_rate=sr, show=False); results['hf_power'] = hrv_f.get('HRV_HF', [np.nan]).iloc[0]; results['lf_hf_ratio'] = hrv_f.get('HRV_LFHF', [np.nan]).iloc[0]
        
        if not np.isnan(results['mean_hr']):
            min_bpm, max_bpm = PLAUSIBLE_RANGES['bpm']
            results['mean_hr'] = np.clip(results['mean_hr'], min_bpm, max_bpm)

        # --- EDA 解析 ---
        signals, info = nk.eda_process((((eda_data / 1023) * 3.3) / 0.132), sampling_rate=sr)
        results['mean_scl'] = signals['EDA_Tonic'].mean()
        
        scr_count = len(info['SCR_Peaks'])
        results['scr_count'] = scr_count
        if duration_sec > 0:
            results['scr_ppm'] = (scr_count / duration_sec) * 60
        else:
            results['scr_ppm'] = 0

        scr_amplitudes = info.get('SCR_Amplitude', [])
        results['scr_amplitude_mean'] = np.nanmean(scr_amplitudes) if len(scr_amplitudes) > 0 else 0.0
        results['scr_amplitude_mean'] = np.nan_to_num(results['scr_amplitude_mean'], nan=0.0)

    except Exception as e:
        print(f"解析中にエラーが発生しました: {e}", file=sys.stderr)
    return results

# ==============================================================================
# 新しいロジック
# ==============================================================================
USE_NEW_PROTOCOL = True

def _decide_level_from_relax(r: float, pour_key: str) -> str:
    thresholds = THRESHOLDS[pour_key]
    if r <= thresholds['low']: return 'low'
    if r >= thresholds['high']: return 'high'
    return 'mid'

def _decide_interval_after_45s(r: float) -> int:
    level = _decide_level_from_relax(r, 'pour_2_interval')
    return INTERVAL_TIME[level]

def _motor_speed_for_valve(valve_sec: float, *, prior_speed: float=None) -> float:
    if prior_speed is not None:
        return float(prior_speed)
    closest_level = min(VALVE_TIME, key=lambda level: abs(VALVE_TIME[level] - valve_sec))
    return MOTOR_SPEED.get(closest_level, MOTOR_SPEED['mid'])

def calculate_relaxation_score(current_metrics, baseline_metrics):
    current_area = np.nan_to_num(current_metrics.get('lorenz_area', baseline_metrics['area_mean']))
    current_scl = np.nan_to_num(current_metrics.get('mean_scl', baseline_metrics['scl_mean']))
    current_ppm = np.nan_to_num(current_metrics.get('scr_ppm', baseline_metrics['ppm_mean']))
    current_amp = np.nan_to_num(current_metrics.get('scr_amplitude_mean', baseline_metrics['amp_mean']))

    area_z = (current_area - baseline_metrics['area_mean']) / baseline_metrics['area_std']
    scl_z = (current_scl - baseline_metrics['scl_mean']) / baseline_metrics['scl_std']
    ppm_z = (current_ppm - baseline_metrics['ppm_mean']) / baseline_metrics['ppm_std']
    amp_z = (current_amp - baseline_metrics['amp_mean']) / baseline_metrics['amp_std']

    area_contrib = np.clip(area_z / 2.0, -1.0, 1.0)
    scl_contrib = np.clip(-scl_z / 2.0, -1.0, 1.0)
    ppm_contrib = np.clip(-ppm_z / 2.0, -1.0, 1.0)
    amp_contrib = np.clip(-amp_z / 2.0, -1.0, 1.0)

    w = RELAXATION_SCORE_WEIGHTS
    composite_score = (area_contrib * w['area'] + scl_contrib * w['scl'] + ppm_contrib * w['scr_count'] + amp_contrib * w['scr_amp'])
    relaxation_score = np.clip(50.0 + composite_score * 45.0, 0, 100)
    print(f"★ 総合リラックス度スコア: {relaxation_score:.1f} / 100 ★")
    return relaxation_score

def collect_and_analyze_data(device, duration, ecg_all, eda_all, sr, label, history, fonts, start_time):
    print(f"\n{duration}秒間のデータを収集中 ({label})...")
    start_loop_time = time.time()
    last_update_time = start_loop_time
    
    while time.time() - start_loop_time < duration:
        if emergency_stop_triggered: raise InterruptedError
        try:
            samples = device.read(nSamples)
            ecg_all.extend(samples[:, 5])
            eda_all.extend(samples[:, 6])
            
            if time.time() - last_update_time > 5.0:
                if history:
                    update_display(history[-1], history, fonts, start_time)
                last_update_time = time.time()
                
            time.sleep(0.1)
        except Exception: pass
        
    print("解析中...")
    analysis_samples = int(duration * sr)
    ecg_chunk = np.array(ecg_all[-analysis_samples:])
    eda_chunk = np.array(eda_all[-analysis_samples:])
    return analyze_interval_data(ecg_chunk, eda_chunk, sr, label)

# ==============================================================================
# --- ▼▼▼修正メインロジック関数▼▼▼ ---
# ==============================================================================
def run_extraction_protocol_v2(device, ecg_all, eda_all, history, fonts, baseline_metrics):
    global emergency_stop_triggered, extraction_start_time
    recipe_plan = []
    result_code_parts = {} # 結果コードの各部分を保存
    
    def _log_and_display(label, r_score, metrics, method_text=None, recipe=None, result_code=None):
        row = {'interval_label': label, 'relaxation_score': r_score, 'method_text': method_text, 'recipe_plan': recipe, 'result_code': result_code, **metrics}
        history.append(row)
        update_display(row, history, fonts, extraction_start_time)

    # ステップ0: ベースライン
    initial_metrics = collect_and_analyze_data(device, 45, ecg_all, eda_all, samplingRate, "安静状態", history, fonts, extraction_start_time)
    
    baseline_metrics.update({
        'area_mean': np.nan_to_num(initial_metrics.get('lorenz_area', 1.0)),
        'scl_mean': np.nan_to_num(initial_metrics.get('mean_scl', 1.0)),
        'ppm_mean': np.nan_to_num(initial_metrics.get('scr_ppm', 0.0)),
        'amp_mean': np.nan_to_num(initial_metrics.get('scr_amplitude_mean', 0.0)),
        'area_std': max(np.nan_to_num(initial_metrics.get('lorenz_area', 1.0)) * 0.1, 50.0),
        'scl_std': max(np.nan_to_num(initial_metrics.get('mean_scl', 1.0)) * 0.1, 0.1),
        'ppm_std': max(np.nan_to_num(initial_metrics.get('scr_ppm', 0.0)) * 0.2, 1.0),
        'amp_std': max(np.nan_to_num(initial_metrics.get('scr_amplitude_mean', 0.0)) * 0.2, 0.05)
    })
    print("基準データを記録しました。")
    _log_and_display("安静状態", 50.0, initial_metrics, recipe=recipe_plan.copy())
    
    # ステップ1: ドライフレグランス
    metrics_1 = collect_and_analyze_data(device, 45, ecg_all, eda_all, samplingRate, "ドライフレグランス", history, fonts, extraction_start_time)
    relax_score_1 = calculate_relaxation_score(metrics_1, baseline_metrics)

    
    # 1投目
    level1 = _decide_level_from_relax(relax_score_1, 'pour_1')
    v1_time = VALVE_TIME[level1]
    m1_speed = MOTOR_SPEED[level1]
    weight1 = TIME_TO_GRAMS[level1]
    v2_time = float((VALVE_TIME['low'] + VALVE_TIME['high']) - v1_time)
    weight2 = 120 - weight1
    method_map_1 = {'low': "sweetness", 'mid': "balance", 'high': "fruity"} # 名称変更
    method_name_1 = method_map_1.get(level1)
    result_code_parts['pour1'] = method_name_1[0].upper()
    method_text_1 = f"{method_name_1}[{weight1}g,{weight2}g]"
    recipe_plan.append(f"0:00 {weight1}g注ぐ")
    _, valve_start_time, motor_thread_1 = start_motor_and_valve_sequence(m1_speed, v1_time)
    if extraction_start_time is None: extraction_start_time = valve_start_time
    _log_and_display("1投目", relax_score_1, metrics_1, method_text_1, recipe_plan.copy())

    # 2投目準備
    metrics_2 = collect_and_analyze_data(device, 30, ecg_all, eda_all, samplingRate, "2投目前", history, fonts, extraction_start_time)
    current_timeline = INTERVAL_TIME['mid']
    remaining_time = (valve_start_time + current_timeline) - time.time()
    if remaining_time > 0: time.sleep(remaining_time)
    relax_score_2 = calculate_relaxation_score(metrics_2, baseline_metrics)
    interval = _decide_interval_after_45s(relax_score_2)
    method_map_2 = {INTERVAL_TIME['low']: "acidity", INTERVAL_TIME['mid']: "normal", INTERVAL_TIME['high']: "bitterness"} # 名称変更
    method_name_2 = method_map_2.get(interval)
    result_code_parts['pour2'] = method_name_2[0].upper()
    method_text_2 = f"{method_name_2}[{interval}sec]"
    if motor_thread_1 and motor_thread_1.is_alive(): motor_thread_1.join()

    # 2投目実行
    m2_speed = _motor_speed_for_valve(v2_time)
    recipe_plan.append(f"{current_timeline // 60}:{current_timeline % 60:02d} {weight2}g注ぐ")
    _, valve_start_time2, motor_thread_2 = start_motor_and_valve_sequence(m2_speed, v2_time)
    _log_and_display("2投目", relax_score_2, metrics_2, method_text_2, recipe_plan.copy())

    # 3投目準備
    metrics_3 = collect_and_analyze_data(device, 30, ecg_all, eda_all, samplingRate, "3投目前", history, fonts, extraction_start_time)
    current_timeline += interval
    remaining_time_3 = (valve_start_time2 + interval) - time.time()
    if remaining_time_3 > 0: time.sleep(remaining_time_3)
    relax_score_3 = calculate_relaxation_score(metrics_3, baseline_metrics)
    if motor_thread_2 and motor_thread_2.is_alive(): motor_thread_2.join()

    # 3投目実行
    level3 = _decide_level_from_relax(relax_score_3, 'pour_3')
    v3_time = VALVE_TIME[level3]      # ★この値を後で使います
    m3_speed = MOTOR_SPEED[level3]    # ★この値を後で使います
    weight3 = TIME_TO_GRAMS[level3]   # ★この値を後で使います
    method_map_3 = {'low': "strong", 'mid': "medium", 'high': "light"} # 名称変更
    method_name_3 = method_map_3.get(level3)
    result_code_parts['pour3'] = method_name_3[0].upper()
    method_text_3 = f"{method_name_3}[{weight3}g]" # 3投目単体の量のみ表示するように変更
    recipe_plan.append(f"{current_timeline // 60}:{current_timeline % 60:02d} {weight3}g注ぐ")
    _, valve_start_time3, motor_thread_3 = start_motor_and_valve_sequence(m3_speed, v3_time)
    _log_and_display("3投目", relax_score_3, metrics_3, method_text_3, recipe_plan.copy())

    # 4投目準備
    metrics_4 = collect_and_analyze_data(device, 30, ecg_all, eda_all, samplingRate, "4投目前", history, fonts, extraction_start_time)
    current_timeline += interval
    remaining_time_4 = (valve_start_time3 + interval) - time.time()
    if remaining_time_4 > 0: time.sleep(remaining_time_4)
    relax_score_4 = calculate_relaxation_score(metrics_4, baseline_metrics)
    if motor_thread_3 and motor_thread_3.is_alive(): motor_thread_3.join()


    # 4投目実行
    # 4投目以降の抽出量は「3投目の量(weight3)」をベースにする
    
    if relax_score_4 < 50.0:
        # 【興奮寄り】5投に延長するシナリオ
        v4_time = v3_time  # 3投目と同じ時間
        weight4 = weight3  # 3投目と同じ量
        method_text_4 = f"thick[total 5 pours, {weight4}g]"
        result_code_parts['pours'] = "5"
    else:
        # 【リラックス寄り】4投で終了するシナリオ
        v4_time = v3_time * 2.0  # 3投目の2倍の時間
        weight4 = weight3 * 2    # 3投目の2倍の量
        method_text_4 = f"thin[total 4 pours, {weight4}g]"
        result_code_parts['pours'] = "4"
        
    m4_speed = m3_speed # モーター速度も3投目と同じにする
    recipe_plan.append(f"{current_timeline // 60}:{current_timeline % 60:02d} {weight4}g注ぐ")
    _, valve_start_time4, motor_thread_4 = start_motor_and_valve_sequence(m4_speed, v4_time)
    _log_and_display("4投目", relax_score_4, metrics_4, method_text_4, recipe_plan.copy())

    # 追加投下準備
    motor_to_join_before_final = motor_thread_4
    final_result_code = ""
    if relax_score_4 < 50.0 and not emergency_stop_triggered: # 興奮寄りの場合のみ5投目を実施
        metrics_5 = collect_and_analyze_data(device, 30, ecg_all, eda_all, samplingRate, "追加投下前", history, fonts, extraction_start_time)
        current_timeline += interval
        remaining_time_5 = (valve_start_time4 + interval) - time.time()
        if remaining_time_5 > 0: time.sleep(remaining_time_5)
        if motor_thread_4 and motor_thread_4.is_alive(): motor_thread_4.join()
        
        # 5投目も「3投目の量」をベースにする
        v5_time = v3_time   # 3投目と同じ時間
        m5_speed = m3_speed # 3投目と同じ速度
        weight5 = weight3   # 3投目と同じ量
        method_text_5 = f"thick[{weight5}g]"
        recipe_plan.append(f"{current_timeline // 60}:{current_timeline % 60:02d} {weight5}g注ぐ")
        _, _, motor_to_join_before_final = start_motor_and_valve_sequence(m5_speed, v5_time)
        _log_and_display("追加", relax_score_4, metrics_5, method_text_5, recipe_plan.copy()) # スコアは4投目のものを表示し、データは5投目前のものを記録
    
    # 最終結果コードの生成と表示
    final_result_code = (result_code_parts.get('pour1', 'X') +
                         result_code_parts.get('pour2', 'X') +
                         result_code_parts.get('pour3', 'X') +
                         result_code_parts.get('pours', 'X'))
    
    current_timeline += interval
    recipe_plan.append(f"{current_timeline // 60}:{current_timeline % 60:02d} ドリッパーを外す")
    history[-1]['recipe_plan'] = recipe_plan
    history[-1]['result_code'] = final_result_code # 最後の履歴に結果コードを追加
    update_display(history[-1], history, fonts, extraction_start_time)

    if motor_to_join_before_final and motor_to_join_before_final.is_alive():
        print("最終的なモーター動作の完了を待機しています...")
        motor_to_join_before_final.join()


# ==============================================================================
# --- メイン実行ブロック ---
# ==============================================================================
if __name__ == '__main__':
    stop_button = Button(EMERGENCY_STOP_BUTTON_PIN, pull_up=True)
    stop_button.when_pressed = emergency_stop
    if macAddress == "XX:XX:XX:XX:XX:XX": sys.exit("エラー: macAddress を設定してください。")
    
    ecg_all_data, eda_all_data, analysis_history = [], [], []
    baseline_metrics = {}
    device = None
    extraction_start_time = None
    
    try:
        device = BITalino(macAddress)
        device.start(samplingRate, acqChannels)
        print(f"--- 生体信号連動アプリケーションを開始します ---")
        print(f"今回の計測ID: {execution_timestamp}")
        update_display({'interval_label': '計測開始待機中...'}, [], fonts, None)

        if USE_NEW_PROTOCOL:
            print("\n--- 新抽出プロトコル (v2) を開始します ---")
            run_extraction_protocol_v2(device, ecg_all_data, eda_all_data, analysis_history, fonts, baseline_metrics)
            print("\n--- 新抽出プロトコル (v2) が完了しました ---")
        else:
            print("従来のプロトコルは現在無効です。")

    except (KeyboardInterrupt, SystemExit, InterruptedError):
        print("\nプログラムがユーザーによって中断されました。")
    except Exception as e:
        print(f"メインループで予期せぬエラーが発生しました: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
    finally:
        if device:
            device.stop()
            device.close()
            print("\nBITalinoデバイスを停止しました。")
        
        print("\n--- 計測完了 ---")

    if analysis_history:
        final_image = update_display(analysis_history[-1], analysis_history, fonts, extraction_start_time)
        os.makedirs(IMG_SAVE_DIRECTORY, exist_ok=True)
        img_path = os.path.join(IMG_SAVE_DIRECTORY, f"final_report_{execution_timestamp}.png")
        try:
            final_image.convert('RGB').save(img_path)
            print(f"\n最終結果の画像を '{img_path}' に保存しました。")
        except Exception as e:
            print(f"画像ファイル保存中にエラーが発生しました: {e}")

    if analysis_history:
        os.makedirs(CSV_SAVE_DIRECTORY, exist_ok=True)
        csv_path = os.path.join(CSV_SAVE_DIRECTORY, f"biofeedback_log_{execution_timestamp}.csv")
        header = list(analysis_history[0].keys())
        if 'lorenz_plot_image' in header: header.remove('lorenz_plot_image')
        if 'recipe_plan' in header: header.remove('recipe_plan')
        try:
            with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=header, extrasaction='ignore')
                writer.writeheader()
                writer.writerows(analysis_history)
            print(f"全解析結果を '{csv_path}' に保存しました。")
        except Exception as e:
            print(f"CSVファイル保存中にエラーが発生しました: {e}")

    print("5秒後にプログラムを終了します...")
    time.sleep(5)
    root.destroy()
