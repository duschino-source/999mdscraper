"""QLoRA/DPO fine-tuning for the local smartphone listing ranker.

Run from a Linux/WSL environment with a CUDA-enabled PyTorch installation.
"""

import argparse
from pathlib import Path

import torch
from datasets import load_dataset
from peft import LoraConfig
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from trl import DPOConfig, DPOTrainer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default="preferences.jsonl", help="DPO JSONL exported by 999scraper-preference")
    parser.add_argument("--model", default="Qwen/Qwen3-0.6B", help="Base model to fine-tune")
    parser.add_argument("--output", default="models/999-ranker", help="Adapter output directory")
    parser.add_argument("--epochs", type=float, default=3)
    args = parser.parse_args()

    if not torch.cuda.is_available():
        raise SystemExit("CUDA GPU not detected. Run this on the GTX 1080 Ti through Linux/WSL with NVIDIA CUDA enabled.")
    if torch.cuda.get_device_properties(0).total_memory < 8 * 1024**3:
        raise SystemExit("At least 8 GB of GPU memory is recommended for this training preset.")
    if not Path(args.data).is_file():
        raise SystemExit(f"Preference dataset not found: {args.data}")

    dataset = load_dataset("json", data_files=args.data, split="train")
    required = {"prompt", "chosen", "rejected"}
    if not required.issubset(dataset.column_names):
        raise SystemExit(f"Dataset must contain these fields: {', '.join(sorted(required))}")
    if len(dataset) < 1:
        raise SystemExit("Record pairwise choices before training; the dataset is empty.")

    quantization = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.float16,
    )
    tokenizer = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForCausalLM.from_pretrained(
        args.model,
        quantization_config=quantization,
        torch_dtype=torch.float16,
        device_map="auto",
    )
    adapter = LoraConfig(
        r=8,
        lora_alpha=16,
        lora_dropout=0.05,
        target_modules="all-linear",
        task_type="CAUSAL_LM",
    )
    training = DPOConfig(
        output_dir=args.output,
        seed=42,
        beta=0.1,
        learning_rate=5e-5,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=8,
        gradient_checkpointing=True,
        max_length=1024,
        max_prompt_length=896,
        logging_steps=5,
        save_strategy="epoch",
        report_to="none",
        fp16=True,
    )
    trainer = DPOTrainer(
        model=model,
        ref_model=None,
        args=training,
        train_dataset=dataset,
        processing_class=tokenizer,
        peft_config=adapter,
    )
    trainer.train()
    trainer.save_model(args.output)
    tokenizer.save_pretrained(args.output)
    print(f"Saved LoRA adapter to {args.output}")


if __name__ == "__main__":
    main()
