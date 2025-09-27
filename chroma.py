import cv2
import numpy as np
from PIL import Image
import os

def hex_to_bgr(hexstr):
    h = hexstr.lstrip('#')
    if len(h)==3:
        h = ''.join([c*2 for c in h])
    r = int(h[0:2],16)
    g = int(h[2:4],16)
    b = int(h[4:6],16)
    return (b,g,r)

def extract_first_frame_hex(video_path, out_frame_path):
    cap = cv2.VideoCapture(video_path)
    ok, frame = cap.read()
    cap.release()
    if not ok or frame is None:
        return False
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    Image.fromarray(frame_rgb).save(out_frame_path)
    return True

def process_video(input_path, output_path,
                  bg_mode='color', chroma_hex='#4287F5', bg_color_hex=None, bg_image_path=None,
                  tolerance=60, blur=7, edge_thin=0, despill_strength=0.3, alpha=1.0):

    if bg_mode == 'image':
        if not bg_image_path or not os.path.exists(bg_image_path):
            raise ValueError("Background image not found")
        bg_img = cv2.imread(bg_image_path, cv2.IMREAD_COLOR)
        if bg_img is None:
            raise ValueError("Невозможно загрузить фоновое изображение")
    else:
        bg_img = None

    cap = cv2.VideoCapture(input_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fourcc = cv2.VideoWriter_fourcc(*'vp80')
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    if bg_img is not None:
        bg_img = cv2.resize(bg_img, (width, height), interpolation=cv2.INTER_AREA)
        bg_arr = bg_img
    else:
        if chroma_hex is not None:
            b, g, r = hex_to_bgr(chroma_hex)
            bg_arr = np.zeros((height, width, 3), dtype=np.uint8)
            bg_arr[:, :] = (b, g, r)
        else:
            bg_arr = np.zeros((height, width, 3), dtype=np.uint8)


    frame_idx = 0
    target_bgr = np.array(hex_to_bgr(bg_color_hex), dtype=np.float32)

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_float = frame.astype(np.float32)
        dist = np.linalg.norm(frame_float - target_bgr.reshape((1,1,3)), axis=2)
        mask = (dist > float(tolerance)).astype(np.uint8) * 255

        if edge_thin != 0:
            ksize = abs(edge_thin)
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ksize*2+1, ksize*2+1))
            if edge_thin > 0:
                mask = cv2.dilate(mask, kernel, iterations=1)
            else:
                mask = cv2.erode(mask, kernel, iterations=1)

        if blur and blur>0:
            if blur % 2 == 0:
                blur += 1
            mask = cv2.GaussianBlur(mask, (blur, blur), 0)

        alpha_m = (mask.astype(np.float32) / 255.0) * float(alpha)

        if despill_strength and despill_strength > 0:
            despill_factor = despill_strength
            fg_factor = alpha_m[..., None]
            frame_float = frame_float - (target_bgr.reshape((1,1,3)) * ( (1 - fg_factor) * despill_factor ))
            frame_float = np.clip(frame_float, 0, 255)

        alpha3 = np.repeat(alpha_m[:,:,None], 3, axis=2)
        comp = (frame_float * alpha3 + bg_arr.astype(np.float32) * (1 - alpha3)).astype(np.uint8)
        
        out.write(comp)
        frame_idx += 1

    cap.release()
    out.release()
