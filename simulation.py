import dataclasses
from typing import List, Tuple

# --- 1. ĐỊNH NGHĨA CẤU TRÚC DỮ LIỆU (UTxO Model) ---


@dataclasses.dataclass
class PoolState:
    """Mô phỏng UTxO của Pool chứa thanh khoản"""

    reserve_a: float  # Số lượng Token A (ví dụ: ADA)
    reserve_b: float  # Số lượng Token B (ví dụ: MIN)
    fee_percent: float = 0.003  # Phí 0.3%

    @property
    def constant_k(self):
        """Hằng số K = x * y (Invariant)"""
        return self.reserve_a * self.reserve_b


@dataclasses.dataclass
class OrderUTxO:
    """Mô phỏng UTxO Lệnh của User gửi lên mạng lưới"""

    user_id: str
    token_in_type: str  # 'A' hoặc 'B'
    amount_in: float
    min_amount_out: float  # Slippage protection (mức chấp nhận tối thiểu)


# --- 2. LOGIC TÍNH TOÁN AMM (Smart Contract Logic) ---


def calculate_swap(pool: PoolState, order: OrderUTxO) -> Tuple[float, float, str]:
    """
    Tính toán số lượng token đầu ra dựa trên công thức Constant Product.
    Trả về: (amount_out, fee_paid, status)
    """
    # Xác định Reserve đầu vào (In) và đầu ra (Out)
    if order.token_in_type == "A":
        reserve_in = pool.reserve_a
        reserve_out = pool.reserve_b
    else:
        reserve_in = pool.reserve_b
        reserve_out = pool.reserve_a

    # 1. Trừ phí giao dịch từ đầu vào
    amount_in_with_fee = order.amount_in * (1 - pool.fee_percent)

    # 2. Công thức AMM: x * y = k
    # new_reserve_in * new_reserve_out = k
    # (reserve_in + amount_in_with_fee) * (reserve_out - amount_out) = reserve_in * reserve_out
    # => amount_out = (amount_in_with_fee * reserve_out) / (reserve_in + amount_in_with_fee)

    numerator = amount_in_with_fee * reserve_out
    denominator = reserve_in + amount_in_with_fee
    amount_out = numerator / denominator

    # 3. Kiểm tra trượt giá (Slippage Check)
    if amount_out < order.min_amount_out:
        return 0.0, 0.0, "REJECTED_SLIPPAGE_TOO_HIGH"

    return amount_out, (order.amount_in - amount_in_with_fee), "SUCCESS"


# --- 3. LOGIC BATCHER (Off-chain Bot) ---


def run_batcher(pool_utxo: PoolState, list_of_orders: List[OrderUTxO]):
    print(f"--- BẮT ĐẦU BATCHING ---")
    print(
        f"TRẠNG THÁI POOL GỐC: A={pool_utxo.reserve_a:.2f} | B={pool_utxo.reserve_b:.2f} | K={pool_utxo.constant_k:.2f}"
    )

    # Batcher gom tất cả lệnh vào một danh sách xử lý
    processed_txs = []

    # Batcher xử lý tuần tự từng lệnh (để tránh tranh chấp trạng thái)
    current_pool = pool_utxo  # Copy trạng thái để cập nhật dần

    for order in list_of_orders:
        print(
            f"\n>> Xử lý lệnh của {order.user_id}: Swap {order.amount_in} Token {order.token_in_type}..."
        )

        amount_out, fee, status = calculate_swap(current_pool, order)

        if status == "SUCCESS":
            # Cập nhật trạng thái Pool (Mutation)
            if order.token_in_type == "A":
                current_pool.reserve_a += order.amount_in
                current_pool.reserve_b -= amount_out
            else:
                current_pool.reserve_b += order.amount_in
                current_pool.reserve_a -= amount_out

            print(f"   -> THÀNH CÔNG! User nhận: {amount_out:.4f} (Phí: {fee:.4f})")
            processed_txs.append(
                {
                    "to": order.user_id,
                    "receive": amount_out,
                    "token": "B" if order.token_in_type == "A" else "A",
                }
            )
        else:
            print(f"   -> THẤT BẠI: {status}. Hoàn trả tiền cho User.")

    # --- 4. TẠO TRANSACTION CUỐI CÙNG (Output Structure) ---
    print("\n" + "=" * 40)
    print("KẾT QUẢ GIAO DỊCH ON-CHAIN (TRANSACTION OUTPUTS)")
    print("=" * 40)

    # Output 1: Pool UTxO Mới
    print(f"[UTxO 0] NEW POOL STATE:")
    print(f"   Reserve A: {current_pool.reserve_a:.4f}")
    print(f"   Reserve B: {current_pool.reserve_b:.4f}")
    print(
        f"   New K    : {current_pool.constant_k:.4f} (Tăng lên do phí thu được -> Lợi nhuận cho LP)"
    )

    # Output 2...n: Trả tiền cho User
    for i, tx in enumerate(processed_txs):
        print(
            f"[UTxO {i+1}] Gửi về ví {tx['to']}: {tx['receive']:.4f} Token {tx['token']}"
        )


# --- CHẠY THỬ ---

# 1. Khởi tạo Pool: 1000 ADA - 2000 MIN (Tỉ lệ 1 ADA = 2 MIN)
my_pool = PoolState(reserve_a=1000, reserve_b=2000)

# 2. Danh sách lệnh đang chờ (Mempool)
orders = [
    # Alice muốn đổi 100 ADA lấy MIN. Kỳ vọng ~200 MIN (chấp nhận tối thiểu 180)
    OrderUTxO("Alice", "A", 100, 180),
    # Bob muốn đổi 500 ADA lấy MIN. Lệnh này LỚN, sẽ gây trượt giá mạnh
    # Bob đòi tối thiểu 900 MIN (vô lý vì 500 ADA lúc này khó đổi được 900 MIN do pool cạn)
    OrderUTxO("Bob", "A", 500, 900),
    # Charlie đổi ngược lại, 50 MIN lấy ADA
    OrderUTxO("Charlie", "B", 50, 20),
]

run_batcher(my_pool, orders)
