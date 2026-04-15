import argparse
import datetime as dt
import hashlib
import json

SECRET_KEY = "ECUFLASH_V1"


def build_payload(machine_code: str, expire_time: str) -> dict:
    return {
        "machine_code": machine_code.strip().upper(),
        "expire_time": expire_time.strip(),
    }


def generate_code(machine_code: str, expire_time: str) -> str:
    payload = build_payload(machine_code, expire_time)
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    payload_hex = raw.encode("utf-8").hex()
    sign = hashlib.md5((raw + SECRET_KEY).encode("utf-8")).hexdigest().upper()
    return payload_hex + sign


def validate_expire_time(value: str) -> str:
    dt.datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="ECUFlash 注册码生成器")
    parser.add_argument("--machine-code", required=True, help="前端显示的机器码")
    parser.add_argument("--expire-time", required=True, type=validate_expire_time, help="到期时间，格式：YYYY-MM-DD HH:MM:SS")
    parser.add_argument("--name", help="仅展示用。注意：前端不会从注册码读取姓名，而是手动输入")
    parser.add_argument("--json", action="store_true", help="同时输出 license.dat 内容示例")
    args = parser.parse_args()

    code = generate_code(args.machine_code, args.expire_time)
    print("注册码:")
    print(code)

    if args.name:
        print("\n前端注册时请填写：")
        print(f"姓名: {args.name}")
        print(f"注册码: {code}")

    if args.json:
        license_data = {
            "machine_code": args.machine_code.strip().upper(),
            "expire_time": args.expire_time,
        }
        if args.name:
            license_data["name"] = args.name
        print("\nlicense.dat 示例内容:")
        print(json.dumps(license_data, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
