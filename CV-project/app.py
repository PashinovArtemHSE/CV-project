import os
import uuid
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, flash
from werkzeug.utils import secure_filename
from chroma import process_video, extract_first_frame_hex, hex_to_bgr
from PIL import Image

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
OUTPUT_FOLDER = os.path.join(BASE_DIR, 'outputs')

for d in (UPLOAD_FOLDER, OUTPUT_FOLDER):
    os.makedirs(d, exist_ok=True)

ALLOWED_VIDEO = {'mp4', 'mov', 'avi', 'mkv', 'webm'}
ALLOWED_IMAGE = {'png', 'jpg', 'jpeg'}

app = Flask(__name__)
app.secret_key = 'change-this-secret'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024

PARAMS_DEFAULT = {
    'tolerance': 60,
    'blur': 7,
    'edge_thin': 0,
    'despill_strength': 0.3,
    'alpha': 1.0
}

def allowed_file(filename, allowed_set):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_set

def normalize_hex(h):
    if not h:
        return ''
    h = h.strip().lstrip('#')
    if len(h) == 3:
        h = ''.join([c*2 for c in h])
    if len(h) != 6:
        return ''
    try:
        int(h, 16)
    except ValueError:
        return ''
    return '#' + h.upper()

def extract_color_from_image(image_path, x, y):
    im = Image.open(image_path).convert('RGB')
    w, h = im.size
    x = max(0, min(x, w-1))
    y = max(0, min(y, h-1))
    r, g, b = im.getpixel((x, y))
    return '#{:02X}{:02X}{:02X}'.format(r, g, b)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        if 'video' not in request.files:
            flash('Файл не выбран')
            return redirect(request.url)
        file = request.files['video']
        if file.filename == '':
            flash('Файл не выбран')
            return redirect(request.url)
        if file and allowed_file(file.filename, ALLOWED_VIDEO):
            fname = secure_filename(file.filename)
            unique = f"{uuid.uuid4().hex}_{fname}"
            save_path = os.path.join(app.config['UPLOAD_FOLDER'], unique)
            file.save(save_path)

            frame_basename = f"{unique}_frame0.png"
            frame_path = os.path.join(app.config['UPLOAD_FOLDER'], frame_basename)
            if not extract_first_frame_hex(save_path, frame_path):
                flash('Не удалось извлечь кадр из видео')
                return redirect(request.url)

            return render_template('pick_color.html',
                                   video_filename=unique,
                                   frame_filename=frame_basename,
                                   params_default=PARAMS_DEFAULT)
        else:
            flash('Неподдерживаемый формат видео')
            return redirect(request.url)
    return render_template('index.html')

@app.route('/pick_color', methods=['POST'])
def pick_color():
    video_filename = request.form.get('video_filename')
    frame_filename = request.form.get('frame_filename')
    if not video_filename or not frame_filename:
        flash('Отсутствуют данные о видео или кадре')
        return redirect(url_for('index'))

    x = request.form.get('frame.x')
    y = request.form.get('frame.y')
    picked_hex = None
    frame_path = os.path.join(app.config['UPLOAD_FOLDER'], frame_filename)

    if x and y:
        try:
            xi, yi = int(float(x)), int(float(y))
            picked_hex = extract_color_from_image(frame_path, xi, yi)
            flash(f'Цвет пикселя: {picked_hex}')
        except:
            flash('Не удалось считать цвет пипеткой')

    manual_hex = request.form.get('bg_hex')
    if manual_hex:
        normalized = normalize_hex(manual_hex)
        if normalized:
            picked_hex = normalized
        else:
            flash('Неверный HEX')

    return render_template('preview.html',
                           video_filename=video_filename,
                           frame_filename=frame_filename,
                           picked_hex=picked_hex,
                           params_default=PARAMS_DEFAULT)

@app.route('/process', methods=['POST'])
def process():
    video_filename = request.form.get('video_filename')
    if not video_filename:
        flash('Видео не указано')
        return redirect(url_for('index'))
    input_path = os.path.join(app.config['UPLOAD_FOLDER'], video_filename)
    if not os.path.exists(input_path):
        flash('Видео не найдено')
        return redirect(url_for('index'))

    bg_mode = request.form.get('bg_mode', 'color')
    bg_color = request.form.get('bg_color', '').strip()
    bg_image_file = request.files.get('bg_image')

    bg_image_path = None
    if bg_mode == 'image' and bg_image_file and bg_image_file.filename != '':
        if allowed_file(bg_image_file.filename, ALLOWED_IMAGE):
            fname = secure_filename(bg_image_file.filename)
            unique = f"{uuid.uuid4().hex}_{fname}"
            bg_image_path = os.path.join(app.config['UPLOAD_FOLDER'], unique)
            bg_image_file.save(bg_image_path)
        else:
            flash('Неподдерживаемый формат фонового изображения')
            return redirect(url_for('index'))

    try:
        tolerance = int(request.form.get('tolerance', PARAMS_DEFAULT['tolerance']))
        blur = int(request.form.get('blur', PARAMS_DEFAULT['blur']))
        edge_thin = int(request.form.get('edge_thin', PARAMS_DEFAULT['edge_thin']))
        despill_strength = float(request.form.get('despill_strength', PARAMS_DEFAULT['despill_strength']))
        alpha = float(request.form.get('alpha', PARAMS_DEFAULT['alpha']))
    except:
        flash('Некорректные параметры')
        return redirect(url_for('index'))

    chroma_hex = normalize_hex(bg_color) or None #новый фон
    bg_color_hex = normalize_hex(request.form.get('picked_hex')) or '#00FF00'  # цвет для удаления

    out_name = f"out_{uuid.uuid4().hex}.webm"
    out_path = os.path.join(app.config['OUTPUT_FOLDER'], out_name)

    try:
        process_video(input_path=input_path,
                      output_path=out_path,
                      bg_mode=bg_mode,
                      chroma_hex=chroma_hex,
                      bg_color_hex=bg_color_hex,
                      bg_image_path=bg_image_path,
                      tolerance=tolerance,
                      blur=blur,
                      edge_thin=edge_thin,
                      despill_strength=despill_strength,
                      alpha=alpha)
    except Exception as e:
        flash('Ошибка обработки видео: ' + str(e))
        return redirect(url_for('index'))

    return render_template('preview.html',
                           processed_video=os.path.basename(out_path),
                           video_filename=video_filename,
                           frame_filename=f"{video_filename}_frame0.png",
                           params_default=PARAMS_DEFAULT)

@app.route('/outputs/<path:filename>')
def outputs(filename):
    return send_from_directory(app.config['OUTPUT_FOLDER'], filename)

@app.route('/downloads/<path:filename>')
def downloads(filename):
    return send_from_directory(app.config['OUTPUT_FOLDER'], filename, as_attachment=True)

if __name__ == '__main__':
    app.run('0.0.0.0', port=5000, debug=True)
