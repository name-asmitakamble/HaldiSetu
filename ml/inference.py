"""
Model inference — the ONLY file the Flask app touches for AI.

CONTRACT between Member 1 (AI) and Member 2 (web app)
-----------------------------------------------------
* Model file : ml/haldisetu_model.keras   (Keras model, softmax output)
* Labels file: ml/class_labels.json       (JSON list, index i = class i, same order as training)
* Input      : RGB image resized to 224x224, float32, RAW pixel values 0-255
               (the Rescaling(1/127.5, -1) MobileNetV2 preprocessing is INSIDE the model,
                see ml/train_mobilenetv2.py — so do not normalise again here)
* Output     : predict(pil_image) -> dict(label, confidence, top3, demo)

If the model file (or TensorFlow) is missing, the predictor runs in DEMO MODE:
it returns a deterministic placeholder so the whole web flow can be tested.
Demo results are flagged (demo=True) and the UI shows a warning. They are NOT real.
"""
import hashlib
import json
import os

IMG_SIZE = (224, 224)
_cache = {}


class Predictor:
    def __init__(self, model_path, labels_path):
        self.model = None
        self.load_error = None
        with open(labels_path, encoding="utf-8") as fh:
            self.labels = json.load(fh)
        if os.path.exists(model_path):
            try:
                import tensorflow as tf  # imported lazily: web app runs without TF in demo mode
                self.model = tf.keras.models.load_model(model_path)
            except Exception as exc:  # noqa: BLE001
                self.load_error = f"{type(exc).__name__}: {exc}"

    @property
    def demo(self):
        return self.model is None

    def predict(self, pil_image):
        img = pil_image.convert("RGB").resize(IMG_SIZE)
        if self.model is not None:
            import numpy as np
            arr = np.asarray(img, dtype="float32")[None, ...]
            probs = [float(p) for p in self.model.predict(arr, verbose=0)[0]]
        else:
            probs = self._demo_probs(img)
        order = sorted(range(len(probs)), key=lambda i: probs[i], reverse=True)
        top3 = [{"label": self.labels[i], "confidence": probs[i]} for i in order[:3]]
        return {
            "label": top3[0]["label"],
            "confidence": top3[0]["confidence"],
            "top3": top3,
            "demo": self.demo,
        }

    def _demo_probs(self, img):
        """Deterministic fake probabilities derived from the image bytes (testing only)."""
        h = hashlib.sha256(img.resize((16, 16)).tobytes()).digest()
        n = len(self.labels)
        raw = [h[i % len(h)] + 1 for i in range(n)]
        raw[h[0] % n] += 400 + h[1]  # make one class dominant; strength varies per image
        total = float(sum(raw))
        return [r / total for r in raw]


def get_predictor(config):
    key = (config["MODEL_PATH"], config["LABELS_PATH"])
    if key not in _cache:
        _cache[key] = Predictor(*key)
    return _cache[key]
