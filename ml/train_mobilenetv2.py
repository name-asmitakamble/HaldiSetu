"""
Train + evaluate the HaldiSetu turmeric-leaf classifier (MobileNetV2 transfer learning).

Needs:  pip install tensorflow numpy scikit-learn      (not needed by the web app in demo mode)
Data :  DATA_DIR/{train,val,test}/<class_name>/*.jpg   (create with ml/split_dataset.py)

Usage:  python ml/train_mobilenetv2.py --data data/turmeric --epochs 12 --fine-tune-epochs 8

Outputs (in ml/):
    haldisetu_model.keras   the model the Flask app loads  (preprocessing is INSIDE the model)
    class_labels.json       class names in training order  (the app + seed.py read this)
    metrics.json            REAL test-set metrics — quote only these numbers in the report/viva

STATUS: written for the project but NOT executed by the web-app author (no dataset / TensorFlow in
the build environment). Member 1 must run it and check the numbers. Do not report accuracy that
this script did not print.
"""
import argparse
import json
import os

import numpy as np
import tensorflow as tf
from sklearn.metrics import classification_report, confusion_matrix
from tensorflow.keras import layers, models
from tensorflow.keras.applications import MobileNetV2

HERE = os.path.dirname(os.path.abspath(__file__))
IMG = (224, 224)
SEED = 42


def load(split_dir, batch, shuffle):
    return tf.keras.utils.image_dataset_from_directory(
        split_dir, image_size=IMG, batch_size=batch, shuffle=shuffle, seed=SEED, label_mode="int")


def class_weights(train_dir, names):
    counts = np.array([len([f for f in os.listdir(os.path.join(train_dir, n))]) for n in names], dtype=float)
    w = counts.sum() / (len(names) * counts)  # "balanced" weighting for imbalanced classes
    return {i: float(x) for i, x in enumerate(w)}


def build(n_classes):
    augment = tf.keras.Sequential([
        layers.RandomFlip("horizontal_and_vertical"), layers.RandomRotation(0.15),
        layers.RandomZoom(0.15), layers.RandomContrast(0.1)], name="augment")
    base = MobileNetV2(input_shape=IMG + (3,), include_top=False, weights="imagenet")
    base.trainable = False
    inp = layers.Input(IMG + (3,), name="raw_pixels_0_255")
    x = augment(inp)                                   # only active during training
    x = layers.Rescaling(1 / 127.5, offset=-1)(x)      # == MobileNetV2 preprocess_input -> [-1, 1]
    x = base(x, training=False)
    x = layers.GlobalAveragePooling2D()(x)
    x = layers.Dropout(0.3)(x)
    out = layers.Dense(n_classes, activation="softmax")(x)
    return models.Model(inp, out), base


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--epochs", type=int, default=12)
    ap.add_argument("--fine-tune-epochs", type=int, default=8)
    ap.add_argument("--batch", type=int, default=32)
    a = ap.parse_args()

    train = load(os.path.join(a.data, "train"), a.batch, True)
    val = load(os.path.join(a.data, "val"), a.batch, False)
    test = load(os.path.join(a.data, "test"), a.batch, False)
    names = train.class_names
    print("Classes:", names)
    cw = class_weights(os.path.join(a.data, "train"), names)
    train, val, test = (d.prefetch(tf.data.AUTOTUNE) for d in (train, val, test))

    model, base = build(len(names))
    cbs = [tf.keras.callbacks.EarlyStopping(patience=4, restore_best_weights=True, monitor="val_loss"),
           tf.keras.callbacks.ReduceLROnPlateau(patience=2, factor=0.3, monitor="val_loss")]

    # Phase 1: train only the new classification head
    model.compile(tf.keras.optimizers.Adam(1e-3), "sparse_categorical_crossentropy", ["accuracy"])
    model.fit(train, validation_data=val, epochs=a.epochs, class_weight=cw, callbacks=cbs)

    # Phase 2: fine-tune the top of MobileNetV2 with a small learning rate
    base.trainable = True
    for layer in base.layers[:-30]:
        layer.trainable = False
    model.compile(tf.keras.optimizers.Adam(1e-5), "sparse_categorical_crossentropy", ["accuracy"])
    model.fit(train, validation_data=val, epochs=a.fine_tune_epochs, class_weight=cw, callbacks=cbs)

    # Final evaluation on the untouched test split
    y_true = np.concatenate([y.numpy() for _, y in test])
    y_pred = np.argmax(model.predict(test, verbose=0), axis=1)
    report = classification_report(y_true, y_pred, target_names=names, output_dict=True, zero_division=0)
    cm = confusion_matrix(y_true, y_pred).tolist()
    print(classification_report(y_true, y_pred, target_names=names, zero_division=0))
    print("Confusion matrix (rows=true, cols=predicted):\n", np.array(cm))

    model.save(os.path.join(HERE, "haldisetu_model.keras"))
    with open(os.path.join(HERE, "class_labels.json"), "w", encoding="utf-8") as fh:
        json.dump(names, fh)
    with open(os.path.join(HERE, "metrics.json"), "w", encoding="utf-8") as fh:
        json.dump({"test_samples": int(len(y_true)), "test_accuracy": report["accuracy"],
                   "per_class": {n: report[n] for n in names}, "confusion_matrix": cm,
                   "class_order": names, "model": "MobileNetV2 transfer learning, 224x224"}, fh, indent=2)
    print("\nSaved model, class_labels.json and metrics.json in", HERE)


if __name__ == "__main__":
    main()
