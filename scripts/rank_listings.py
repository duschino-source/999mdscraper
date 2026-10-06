"""Rank a JSON export of listings with a locally fine-tuned QLoRA adapter."""

import argparse
import json
import re
from functools import cmp_to_key
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig


def listing_text(item):
    price = item.get("price")
    price_text = "unknown" if price is None else f"{price} {item.get('currency') or ''}".strip()
    return (
        f"Title: {item.get('title') or 'unknown'}\nPrice: {price_text}\n"
        f"Description: {item.get('description') or 'unknown'}\nURL: {item.get('url') or ''}"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="JSON listing export from 999scraper")
    parser.add_argument("--criteria", default="smartphone-criteria.json")
    parser.add_argument("--adapter", default="models/999-ranker")
    parser.add_argument("--model", default="Qwen/Qwen3-0.6B")
    parser.add_argument("--output", default="ranked-listings.json")
    args = parser.parse_args()

    if not torch.cuda.is_available():
        raise SystemExit("CUDA GPU not detected; run with NVIDIA CUDA enabled.")
    listings = json.loads(Path(args.input).read_text(encoding="utf-8"))
    if not isinstance(listings, list):
        raise SystemExit("Input must be a JSON array of listings.")
    if len(listings) < 2:
        raise SystemExit("At least two listings are needed for comparison.")
    criteria = json.loads(Path(args.criteria).read_text(encoding="utf-8"))
    quantization = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.float16,
    )
    tokenizer = AutoTokenizer.from_pretrained(args.model)
    base = AutoModelForCausalLM.from_pretrained(
        args.model,
        quantization_config=quantization,
        torch_dtype=torch.float16,
        device_map="auto",
    )
    model = PeftModel.from_pretrained(base, args.adapter)
    model.eval()

    def prefers(left, right):
        prompt = {
            "task": f"Choose the better {criteria.get('category', 'items')} listing using the user's preset criteria.",
            "criteria": criteria,
            "listing_a": listing_text(left),
            "listing_b": listing_text(right),
            "instruction": "Reply with only A or B.",
        }
        encoded = tokenizer(json.dumps(prompt, ensure_ascii=False), return_tensors="pt")
        encoded = {key: value.to(model.device) for key, value in encoded.items()}
        with torch.inference_mode():
            result = model.generate(**encoded, max_new_tokens=4, do_sample=False)
        answer = tokenizer.decode(
            result[0][encoded["input_ids"].shape[1]:], skip_special_tokens=True
        ).strip().upper()
        match = re.search(r"\b([AB])\b", answer)
        if not match:
            return False
        return match.group(1) == "A"

    def compare(left, right):
        if prefers(left, right):
            return -1
        return 1

    ranked = sorted(listings, key=cmp_to_key(compare))
    output = [{**item, "rank": index} for index, item in enumerate(ranked, start=1)]
    Path(args.output).write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Ranked {len(output)} listings into {args.output}")


if __name__ == "__main__":
    main()
