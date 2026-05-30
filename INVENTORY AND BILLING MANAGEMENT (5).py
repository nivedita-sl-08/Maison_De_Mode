
 

# MaisonDeMode.py
# pastel beige theme, GST, PDF invoices (fallback CSV), returns

import os
import csv
import sys
import random
import string
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog

# Try reportlab for PDF invoices
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    REPORTLAB = True
except Exception:
    REPORTLAB = False

# ----------------------------
# Config & Globals
# ----------------------------
INVENTORY_FILE = "inventory.csv"
ACCOUNTING_FILE = "accounting.csv"
PROFIT_LOSS_FILE = "profit_loss.csv"
RECEIPT_NO_FILE = "receipt_no.txt"
RECEIPT_DIR = "receipts"
os.makedirs(RECEIPT_DIR, exist_ok=True)

STORE_NAME = "Maison de Mode"
STORE_ADDRESS = "14 Rue de la Mode, Bengaluru – 560001"
STORE_PHONE = "+91 90000 00000"
STORE_GSTIN = "29MMODE1234F1Z9"

# Theme colors & fonts
BG_COLOR = "#f5efe6"      # pastel beige
CARD_BG = "#fbf8f2"       # off-white card
ACCENT = "#c1a57b"        # gold-taupe
TEXT = "#2f2f2f"          # deep gray
FONT_TITLE = ("Georgia", 24, "bold")
FONT_SUB = ("Georgia", 11)
FONT_BTN = ("Georgia", 12)
FONT_MONO = ("Courier New", 10)

# Global inventory structure: code -> {category, name, quantity, price}
inventory = {}

# ----------------------------
# Utility functions
# ----------------------------
def generate_code(length=6):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

def robust_int(x, default=0):
    try:
        return int(float(str(x).strip()))
    except:
        return default

def robust_float(x, default=0.0):
    try:
        return float(str(x).replace("₹","").strip())
    except:
        cleaned = ''.join(ch for ch in str(x) if (ch.isdigit() or ch in ".-"))
        try:
            return float(cleaned) if cleaned else default
        except:
            return default

# ----------------------------
# Receipt number management
# ----------------------------
def ensure_receipt_file():
    if not os.path.exists(RECEIPT_NO_FILE):
        with open(RECEIPT_NO_FILE, "w", encoding="utf-8") as f:
            f.write("1000")

def get_receipt_no():
    ensure_receipt_file()
    with open(RECEIPT_NO_FILE, "r+", encoding="utf-8") as f:
        txt = f.read().strip()
        try:
            num = int(txt)
        except:
            num = 1000
        next_num = num + 1
        f.seek(0)
        f.write(str(next_num))
        f.truncate()
    return num

# ----------------------------
# Inventory I/O
# ----------------------------
def load_inventory():
    global inventory
    inventory = {}
    if not os.path.exists(INVENTORY_FILE):
        # create file with header
        with open(INVENTORY_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Code","Category","Name","Quantity","Price"])
        return
    with open(INVENTORY_FILE, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = (row.get("Code") or "").strip()
            if not code:
                continue
            category = (row.get("Category") or "").strip() or "Uncategorized"
            name = (row.get("Name") or "").strip() or "Unnamed"
            qty = robust_int(row.get("Quantity", 0), 0)
            price = robust_float(row.get("Price", 0.0), 0.0)
            inventory[code] = {"category": category, "name": name, "quantity": qty, "price": price}

def save_inventory():
    with open(INVENTORY_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Code","Category","Name","Quantity","Price"])
        for code, item in inventory.items():
            writer.writerow([code, item.get("category",""), item.get("name",""), int(item.get("quantity",0)), float(item.get("price",0.0))])

# ----------------------------
# Accounting & Profit/Loss
# ----------------------------
def update_accounting():
    total_inventory_cost = 0.0
    with open(ACCOUNTING_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Category","Item Name","Quantity","Unit Price","Total Cost"])
        for code, item in inventory.items():
            qty = item.get("quantity", 0)
            unit = item.get("price", 0.0)
            total_cost = qty * unit
            writer.writerow([item.get("category",""), item.get("name",""), qty, f"{unit:.2f}", f"{total_cost:.2f}"])
            total_inventory_cost += total_cost
        writer.writerow([])
        writer.writerow(["TOTAL INVENTORY COST", "", "", "", f"{total_inventory_cost:.2f}"])
    return total_inventory_cost

def append_profit_loss(timestamp, category, item_name, quantity, cost_price, selling_price, gst_collected=0.0):
    header_needed = not os.path.exists(PROFIT_LOSS_FILE) or os.path.getsize(PROFIT_LOSS_FILE) == 0
    diff_per_item = selling_price - cost_price
    total_diff = diff_per_item * quantity

    # determine profit/loss/even
    if total_diff > 0:
        status = "PROFIT"
    elif total_diff < 0:
        status = "LOSS"
    else:
        status = "EVEN"

    with open(PROFIT_LOSS_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if header_needed:
            writer.writerow([
                "Date & Time","Category","Item","Quantity",
                "Cost Price","Selling Price","Diff per Item","Total Diff","GST Collected","Status"
            ])
        writer.writerow([
            timestamp, category, item_name, quantity,
            f"{cost_price:.2f}", f"{selling_price:.2f}",
            f"{diff_per_item:.2f}", f"{total_diff:.2f}", f"{gst_collected:.2f}", status
        ])


# ----------------------------
# GST rules
# Accessories -> 18%
# Clothing: <=999 -> 5%, >=1000 -> 12%
# ----------------------------
def gst_rate_for_item(unit_price, category_hint=""):
    cat = (category_hint or "").lower()
    if "access" in cat:
        return 0.18
    up = robust_float(unit_price, 0.0)
    if up <= 999:
        return 0.05
    else:
        return 0.12

# ----------------------------
# Invoice generation (PDF via reportlab or CSV fallback)
# ----------------------------
def create_invoice_file(receipt_no, items, subtotal, gst_total, grand_total, payment_method, save_dir=RECEIPT_DIR):
    os.makedirs(save_dir, exist_ok=True)
    pdf_path = os.path.join(save_dir, f"invoice_{receipt_no}.pdf")
    csv_path = os.path.join(save_dir, f"invoice_{receipt_no}.csv")

    if REPORTLAB:
        try:
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.cidfonts import UnicodeCIDFont
            from reportlab.lib.pagesizes import A4

            # ✅ Register font that supports ₹ on macOS
            pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
            font_name = "STSong-Light"

            c = canvas.Canvas(pdf_path, pagesize=A4)
            width, height = A4
            margin = 50
            x = margin
            y = height - margin

            # === Header ===
            c.setFont(font_name, 18)
            c.drawCentredString(width / 2, y, STORE_NAME)
            y -= 22
            c.setFont(font_name, 10)
            c.drawCentredString(width / 2, y, STORE_ADDRESS)
            y -= 12
            c.drawCentredString(width / 2, y, f"Phone: {STORE_PHONE}    GSTIN: {STORE_GSTIN}")
            y -= 25

            # === Invoice details ===
            c.setFont(font_name, 10)
            c.drawString(x, y, f"Invoice No: {receipt_no}")
            c.drawRightString(width - margin, y, datetime.now().strftime("Date: %Y-%m-%d  %H:%M"))
            y -= 18
            c.drawString(x, y, f"Payment Method: {payment_method}")
            y -= 20

            # === Table header ===
            c.setFont(font_name, 9)
            headers = ["SNo", "Category", "Item", "Qty", "Unit ₹", "GST ₹", "Line Total ₹"]
            # shifted inward for macOS preview margins
            colx = [x, x + 35, x + 130, x + 300, x + 370, x + 440, x + 500]

            for hx, hv in zip(colx, headers):
                c.drawString(hx, y, hv)
            y -= 10
            c.line(x, y, width - margin, y)
            y -= 12

            # === Table content ===
            c.setFont(font_name, 9)
            for i, it in enumerate(items, start=1):
                if y < margin + 100:
                    c.showPage()
                    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
                    c.setFont(font_name, 9)
                    y = height - margin
                c.drawString(colx[0], y, str(i))
                c.drawString(colx[1], y, it.get("category", "")[:15])
                c.drawString(colx[2], y, it.get("name", "")[:25])
                c.drawRightString(colx[3] + 15, y, str(it.get("qty", 0)))
                c.drawRightString(colx[4] + 25, y, f"₹{it.get('unit_price', 0):.2f}")
                c.drawRightString(colx[5] + 25, y, f"₹{it.get('gst', 0):.2f}")
                c.drawRightString(colx[6] + 40, y, f"₹{it.get('line_total', 0):.2f}")
                y -= 14

            # === Totals ===
            y -= 10
            c.line(x, y, width - margin, y)
            y -= 18
            c.setFont(font_name, 11)
            c.drawRightString(width - margin - 140, y, "Subtotal:")
            c.drawRightString(width - margin, y, f"₹{subtotal:.2f}")
            y -= 16
            c.drawRightString(width - margin - 140, y, "GST Total:")
            c.drawRightString(width - margin, y, f"₹{gst_total:.2f}")
            y -= 18
            c.setFont(font_name, 12)
            c.drawRightString(width - margin - 140, y, "Grand Total:")
            c.drawRightString(width - margin, y, f"₹{grand_total:.2f}")
            y -= 30

            # === Footer ===
            c.setFont(font_name, 9)
            c.drawCentredString(width / 2, y, "Thank you for shopping at Maison de Mode.")
            c.save()
            return True, pdf_path

        except Exception as e:
            print("PDF invoice failed:", e)

    # === CSV Fallback ===
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["SNo", "Category", "Item", "Qty", "Unit Price", "GST", "Line Total"])
        for i, it in enumerate(items, start=1):
            writer.writerow([
                i,
                it.get("category", ""),
                it.get("name", ""),
                it.get("qty", 0),
                f"{it.get('unit_price', 0):.2f}",
                f"{it.get('gst', 0):.2f}",
                f"{it.get('line_total', 0):.2f}"
            ])
        writer.writerow([])
        writer.writerow(["Subtotal", "", "", "", "", "", f"{subtotal:.2f}"])
        writer.writerow(["GST Total", "", "", "", "", "", f"{gst_total:.2f}"])
        writer.writerow(["Grand Total", "", "", "", "", "", f"{grand_total:.2f}"])
        writer.writerow([])
        writer.writerow(["Payment Method", payment_method])
        writer.writerow(["Thank you for shopping at Maison de Mode."])
    return True, csv_path



# ----------------------------
# GUI: main window
# ----------------------------
load_inventory()
update_accounting()

root = tk.Tk()
root.title(f"{STORE_NAME} — Inventory & Billing")
root.geometry("980x720")
root.configure(bg=BG_COLOR)

# Header
lbl_title = tk.Label(root, text=STORE_NAME, font=FONT_TITLE, bg=BG_COLOR, fg=TEXT)
lbl_title.pack(pady=(18,4))
lbl_sub = tk.Label(root, text="Inventory & Billing Management", font=FONT_SUB, bg=BG_COLOR, fg=TEXT)
lbl_sub.pack(pady=(0,12))

# Card frame: left controls + right summary
card = tk.Frame(root, bg=CARD_BG, bd=0)
card.pack(padx=24, pady=12, fill="both", expand=True)

# Helper to create buttons consistently
def make_button(parent, text, cmd):
    b = tk.Button(parent, text=text, command=cmd, font=FONT_BTN, bg=ACCENT, fg=TEXT,
                  activebackground="#b89866", activeforeground=TEXT, bd=0, width=22, height=2)
    return b

# Controls (left)
controls = tk.Frame(card, bg=CARD_BG)
controls.pack(side="left", fill="y", padx=12, pady=12)

# Summary text (right)
summary_frame = tk.Frame(card, bg=CARD_BG)
summary_frame.pack(side="right", fill="both", expand=True, padx=12, pady=12)
summary_text = tk.Text(summary_frame, height=20, state="disabled", font=FONT_MONO, bg="#fffdf8", fg=TEXT, bd=0)
summary_text.pack(fill="both", expand=True, padx=6, pady=6)

def refresh_summary():
    load_inventory()
    lines = []
    lines.append("=== INVENTORY SUMMARY ===\n\n")
    for code, it in inventory.items():
        lines.append(f"{code:<8} {it.get('category','')[:12]:<12} {it.get('name','')[:28]:<28} {it.get('quantity',0):>5}  ₹{it.get('price',0.0):>8.2f}\n")
    summary_text.configure(state="normal")
    summary_text.delete("1.0", tk.END)
    summary_text.insert(tk.END, "".join(lines))
    summary_text.configure(state="disabled")

refresh_summary()

# ----------------------------
# Add Item action
# ----------------------------

def add_item_gui():
    add_win = tk.Toplevel(root)
    add_win.title("Add New Item")
    add_win.configure(bg=BG_COLOR)
    add_win.geometry("400x460")
    add_win.resizable(False, False)

    tk.Label(
        add_win,
        text="Add New Inventory Item",
        font=("Georgia", 16, "bold"),
        bg=BG_COLOR,
        fg=TEXT
    ).pack(pady=(15, 8))

    fields = {
        "Category (Men/Women/Accessories)": tk.StringVar(),
        "Item Code": tk.StringVar(),
        "Item Name": tk.StringVar(),
        "Quantity": tk.StringVar(),
        "Unit Price (₹)": tk.StringVar()
    }

    form_frame = tk.Frame(add_win, bg=CARD_BG, bd=2, relief="groove")
    form_frame.pack(padx=20, pady=10, fill="x", expand=True)

    for label, var in fields.items():
        row = tk.Frame(form_frame, bg=CARD_BG)
        row.pack(fill="x", padx=12, pady=6)
        tk.Label(
            row,
            text=label,
            font=("Georgia", 10, "bold"),
            bg=CARD_BG,
            fg=TEXT
        ).pack(anchor="w")
        ttk.Entry(row, textvariable=var, font=FONT_SUB).pack(fill="x", pady=3)

    def save_item():
        cat = fields["Category (Men/Women/Accessories)"].get().strip()
        code = fields["Item Code"].get().strip().upper()
        name = fields["Item Name"].get().strip()
        qty = fields["Quantity"].get().strip()
        price = fields["Unit Price (₹)"].get().strip()

        if not all([cat, code, name, qty, price]):
            messagebox.showerror("Error", "Please fill in all fields.")
            return

        if code in inventory:
            messagebox.showwarning("Duplicate Code", f"Item code '{code}' already exists.")
            return

        try:
            qty = int(qty)
            price = float(price)
        except ValueError:
            messagebox.showerror("Error", "Invalid quantity or price.")
            return

        inventory[code] = {"category": cat, "name": name, "quantity": qty, "price": price}
        save_inventory()
        update_accounting()
        refresh_summary()

        messagebox.showinfo(
            "Success",
            f"Added item:\n\n{code} – {name}\nCategory: {cat}\nQty: {qty}\nPrice: ₹{price:.2f}"
        )
        add_win.destroy()

    # Button frame (bottom aligned)
    btn_frame = tk.Frame(add_win, bg=BG_COLOR)
    btn_frame.pack(pady=15, side="bottom")
    ttk.Button(btn_frame, text="Add Item", command=save_item).pack(pady=5)



# ----------------------------
# View Inventory action
# ----------------------------
def view_inventory_window():
    load_inventory()
    w = tk.Toplevel(root)
    w.title("Inventory — Maison de Mode")
    w.geometry("860x520")
    w.configure(bg=BG_COLOR)
    lbl = tk.Label(w, text="Inventory List", font=("Georgia", 16, "bold"), bg=BG_COLOR, fg=TEXT)
    lbl.pack(pady=8)
    cols = ("Code","Category","Name","Qty","Price")
    tree = ttk.Treeview(w, columns=cols, show="headings", height=18)
    for c in cols:
        tree.heading(c, text=c)
        tree.column(c, anchor="center", width=140 if c!="Name" else 300)
    tree.pack(fill="both", padx=12, pady=8, expand=True)
    for code, it in inventory.items():
        tree.insert("", "end", values=(code, it.get("category",""), it.get("name",""), it.get("quantity",0), f"{it.get('price',0.0):.2f}"))

# ----------------------------
# Billing window (left/right layout)
# ----------------------------
def open_billing_window():
    load_inventory()
    bw = tk.Toplevel(root)
    bw.title("Billing — Maison de Mode")
    bw.geometry("1100x720")
    bw.configure(bg=BG_COLOR)

    left = tk.Frame(bw, bg=CARD_BG)
    left.pack(side="left", fill="both", expand=True, padx=12, pady=12)

    right = tk.Frame(bw, bg=BG_COLOR)
    right.pack(side="right", fill="y", padx=12, pady=12)

    # Inventory tree (left)
    cols = ("Code","Category","Name","Qty","Price")
    inv_tree = ttk.Treeview(left, columns=cols, show="headings", height=22)
    for c in cols:
        inv_tree.heading(c, text=c)
        inv_tree.column(c, anchor="center", width=130 if c!="Name" else 320)
    inv_tree.pack(fill="both", expand=True, padx=8, pady=8)
    for code, it in inventory.items():
        inv_tree.insert("", "end", values=(code, it.get("category",""), it.get("name",""), it.get("quantity",0), f"{it.get('price',0.0):.2f}"))

    # Right-side controls
    sel_var = tk.StringVar(value="None selected")
    tk.Label(right, textvariable=sel_var, bg=BG_COLOR, fg=TEXT).pack(anchor="w", pady=(6,2))

    tk.Label(right, text="Quantity:", bg=BG_COLOR, fg=TEXT).pack(anchor="w")
    qty_spin = tk.Spinbox(right, from_=1, to=9999, width=8)
    qty_spin.pack(anchor="w", pady=4)

    tk.Label(right, text="Selling price per unit (₹):", bg=BG_COLOR, fg=TEXT).pack(anchor="w")
    price_entry = tk.Entry(right, width=12)
    price_entry.pack(anchor="w", pady=4)

    cart_tree = ttk.Treeview(right, columns=("Item","Qty","Unit","Subtotal","GST","Total"), show="headings", height=12)
    for c in ("Item","Qty","Unit","Subtotal","GST","Total"):
        cart_tree.heading(c, text=c)
        cart_tree.column(c, anchor="center", width=110)
    cart_tree.pack(pady=8)

    subtotal_var = tk.StringVar(value="₹0.00")
    gst_var = tk.StringVar(value="₹0.00")
    total_var = tk.StringVar(value="₹0.00")
    tk.Label(right, text="Subtotal (Pre-GST):", bg=BG_COLOR, fg=TEXT).pack(anchor="w")
    tk.Label(right, textvariable=subtotal_var, bg=BG_COLOR, fg=TEXT, font=("Georgia",11,"bold")).pack(anchor="w")
    tk.Label(right, text="Total GST:", bg=BG_COLOR, fg=TEXT).pack(anchor="w")
    tk.Label(right, textvariable=gst_var, bg=BG_COLOR, fg=TEXT, font=("Georgia",11,"bold")).pack(anchor="w")
    tk.Label(right, text="Grand Total:", bg=BG_COLOR, fg=TEXT).pack(anchor="w")
    tk.Label(right, textvariable=total_var, bg=BG_COLOR, fg=TEXT, font=("Georgia",12,"bold")).pack(anchor="w", pady=(0,8))

    cart = []

    def on_inv_select(event):
        sel = inv_tree.focus()
        if not sel:
            return
        code, cat, name, qty_avail, price = inv_tree.item(sel, "values")
        sel_var.set(f"{name} ({code}) — {cat} — Available: {qty_avail}")
        price_entry.delete(0, tk.END)
        price_entry.insert(0, price)

    inv_tree.bind("<<TreeviewSelect>>", on_inv_select)

    def refresh_inv_tree():
        for r in inv_tree.get_children():
            inv_tree.delete(r)
        for code, it in inventory.items():
            inv_tree.insert("", "end", values=(code, it.get("category",""), it.get("name",""), it.get("quantity",0), f"{it.get('price',0.0):.2f}"))

    def refresh_cart_ui():
        cart_tree.delete(*cart_tree.get_children())
        subtotal = sum(it["subtotal"] for it in cart)
        gst_total = sum(it["gst"] for it in cart)
        grand = subtotal + gst_total
        for it in cart:
            cart_tree.insert("", "end", values=(it["name"][:24], it["qty"], f"₹{it['unit_price']:.2f}", f"₹{it['subtotal']:.2f}", f"₹{it['gst']:.2f}", f"₹{it['line_total']:.2f}"))
        subtotal_var.set(f"₹{subtotal:.2f}")
        gst_var.set(f"₹{gst_total:.2f}")
        total_var.set(f"₹{grand:.2f}")

    def add_to_cart():
        sel = inv_tree.focus()
        if not sel:
            messagebox.showerror("Error","Select an inventory item first.")
            return
        code, cat, name, qty_avail, price_str = inv_tree.item(sel, "values")
        try:
            qty_buy = int(qty_spin.get())
            sell_price = float(price_entry.get())
        except:
            messagebox.showerror("Error","Enter valid quantity and price.")
            return
        qty_avail = robust_int(qty_avail, 0)
        if qty_buy <= 0:
            messagebox.showerror("Error","Quantity must be >= 1.")
            return
        if qty_buy > qty_avail:
            messagebox.showerror("Error", f"Only {qty_avail} available.")
            return
        rate = gst_rate_for_item(sell_price, cat)
        line_sub = round(sell_price * qty_buy, 2)
        line_gst = round(line_sub * rate, 2)
        line_total = round(line_sub + line_gst, 2)
        if code in inventory:
            inventory[code]["quantity"] -= qty_buy
        else:
            inventory[code] = {"category": cat, "name": name, "quantity": 0, "price": sell_price}
        save_inventory()
        cart.append({
            "code": code, "category": cat, "name": name,
            "qty": qty_buy, "unit_price": sell_price,
            "subtotal": line_sub, "gst": line_gst, "line_total": line_total
        })
        refresh_inv_tree()
        refresh_cart_ui()
        refresh_summary()

    btn_addcart = make_button(right, "Add to Cart", add_to_cart)
    btn_addcart.pack(pady=(6,6))

    def remove_cart_item():
        sel = cart_tree.focus()
        if not sel:
            messagebox.showerror("Error","Select cart item to remove.")
            return
        idx = list(cart_tree.get_children()).index(sel)
        itm = cart.pop(idx)
        if itm["code"] in inventory:
            inventory[itm["code"]]["quantity"] += itm["qty"]
        else:
            inventory[itm["code"]] = {"category": itm.get("category",""), "name": itm.get("name",""), "quantity": itm["qty"], "price": itm.get("unit_price",0.0)}
        save_inventory()
        refresh_inv_tree()
        refresh_cart_ui()
        refresh_summary()

    btn_remcart = make_button(right, "Remove Cart Item", remove_cart_item)
    btn_remcart.pack(pady=(6,6))

    def proceed_to_payment():
        if not cart:
            messagebox.showerror("Error","Cart is empty.")
            return
        pay_win = tk.Toplevel(bw)
        pay_win.title("Payment Method")
        pay_win.geometry("340x220")
        pay_win.configure(bg=BG_COLOR)
        tk.Label(pay_win, text="Choose Payment Method", font=("Georgia",12,"bold"), bg=BG_COLOR, fg=TEXT).pack(pady=10)
        pm_var = tk.StringVar(value="Cash")
        for opt in ("Cash","Card","UPI"):
            ttk.Radiobutton(pay_win, text=opt, variable=pm_var, value=opt).pack(anchor="w", padx=20, pady=6)

        def do_payment():
            method = pm_var.get()
            if method == "Cash":
                messagebox.showinfo("Payment","Cash received. Completing sale...")
                finalize_sale(method)
                pay_win.destroy()
            elif method == "Card":
                messagebox.showinfo("Payment","Processing card transaction...")
                pay_win.after(1100, lambda: [messagebox.showinfo("Card","Card approved."), finalize_sale(method), pay_win.destroy()])
            elif method == "UPI":
                upi = simpledialog.askstring("UPI ID", "Enter UPI ID (e.g. name@bank):", parent=pay_win)
                if not upi:
                    messagebox.showerror("UPI", "No UPI entered.")
                    return
                messagebox.showinfo("UPI", f"Verifying UPI ID {upi}...")
                pay_win.after(1000, lambda: [messagebox.showinfo("UPI","Payment successful via UPI."), finalize_sale(f"UPI ({upi})"), pay_win.destroy()])

        ttk.Button(pay_win, text="Pay", command=do_payment).pack(pady=12)

    btn_pay = make_button(right, "Proceed to Payment", proceed_to_payment)
    btn_pay.pack(pady=(8,8))

    def finalize_sale(payment_method):
        rno = get_receipt_no()
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        subtotal = sum(i["subtotal"] for i in cart)
        gst_total = sum(i["gst"] for i in cart)
        grand = subtotal + gst_total

        # save receipt csv
        receipt_path = os.path.join(RECEIPT_DIR, f"receipt_{rno}.csv")
        with open(receipt_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["Receipt No", rno])
            w.writerow(["Date & Time", ts])
            w.writerow([])
            w.writerow(["Category","Code","Item","Qty","UnitPrice","Subtotal","GST","LineTotal"])
            for it in cart:
                w.writerow([it["category"], it["code"], it["name"], it["qty"], f"{it['unit_price']:.2f}", f"{it['subtotal']:.2f}", f"{it['gst']:.2f}", f"{it['line_total']:.2f}"])
            w.writerow([])
            w.writerow(["Grand Subtotal", f"{subtotal:.2f}"])
            w.writerow(["Grand GST", f"{gst_total:.2f}"])
            w.writerow(["Grand Total", f"{grand:.2f}"])
            w.writerow(["Payment Method", payment_method])

        # profit/loss entries (pre-GST)
        for it in cart:
            cost_price = inventory.get(it["code"], {}).get("price", it["unit_price"])
            append_profit_loss(ts, it["category"], it["name"], it["qty"], cost_price, it["unit_price"], gst_collected=it["gst"])

        # create invoice
        invoice_items = []
        for it in cart:
            invoice_items.append({
                "category": it["category"], "code": it["code"], "name": it["name"],
                "qty": it["qty"], "unit_price": it["unit_price"], "subtotal": it["subtotal"],
                "gst": it["gst"], "line_total": it["line_total"]
            })
        ok, path = create_invoice_file(rno, invoice_items, subtotal, gst_total, grand, payment_method)
        update_accounting()
        save_inventory()
        refresh_summary()
        messagebox.showinfo("Sale Complete", f"Receipt saved: {receipt_path}\nInvoice: {path if ok else 'Failed: '+str(path)}\nTotal: ₹{grand:.2f}")
        bw.destroy()

# ----------------------------
# Returns, Accounting, Profit/Loss windows
# ----------------------------
def open_receipts_folder():
    try:
        if sys.platform.startswith("win"):
            os.startfile(RECEIPT_DIR)
        elif sys.platform.startswith("darwin"):
            os.system(f'open "{RECEIPT_DIR}"')
        else:
            os.system(f'xdg-open "{RECEIPT_DIR}"')
    except Exception as e:
        messagebox.showerror("Error", f"Could not open receipts folder: {e}")

def open_return_window():
    receipts = sorted([f for f in os.listdir(RECEIPT_DIR) if f.lower().endswith(".csv")])
    if not receipts:
        messagebox.showinfo("Returns", "No receipts to return from.")
        return
    w = tk.Toplevel(root)
    w.title("Return Items")
    w.geometry("820x560")
    w.configure(bg=BG_COLOR)

    top = tk.Frame(w, bg=BG_COLOR)
    top.pack(fill="x", padx=10, pady=6)
    tk.Label(top, text="Select receipt:", font=("Georgia",11), bg=BG_COLOR, fg=TEXT).pack(side="left")
    cb = ttk.Combobox(top, values=receipts, state="readonly", width=60)
    cb.pack(side="left", padx=8)
    cb.set(receipts[-1])

    cols = ("Category","Code","Item","Qty","UnitPrice","Subtotal","GST","LineTotal")
    tree = ttk.Treeview(w, columns=cols, show="headings", selectmode="extended")
    for c in cols:
        tree.heading(c, text=c)
        tree.column(c, anchor="center", width=110 if c!="Item" else 260)
    tree.pack(fill="both", expand=True, padx=12, pady=8)

    def load_receipt(ev=None):
        sel = cb.get()
        if not sel:
            return
        path = os.path.join(RECEIPT_DIR, sel)
        tree.delete(*tree.get_children())
        try:
            with open(path, "r", encoding="utf-8") as f:
                rows = list(csv.reader(f))
                start = None
                for i, r in enumerate(rows):
                    if r and r[0].strip().lower() == "category":
                        start = i+1
                        break
                if start is None:
                    messagebox.showerror("Format", "Receipt format not recognized.")
                    return
                for r in rows[start:]:
                    if not r: break
                    if r[0].strip().lower().startswith("grand"): break
                    rpad = r + [""]*(8-len(r))
                    tree.insert("", "end", values=tuple(rpad[:8]))
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load receipt: {e}")

    cb.bind("<<ComboboxSelected>>", load_receipt)
    load_receipt()

    def return_selected():
        sel = tree.selection()
        if not sel:
            messagebox.showerror("Error","Select lines to return.")
            return
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        returned = 0
        for s in sel:
            vals = tree.item(s, "values")
            try:
                cat, code, name, qty_str, unit_price_str = vals[0], vals[1], vals[2], vals[3], vals[4]
                qty = robust_int(qty_str, 0)
                unit_price = robust_float(unit_price_str, 0.0)
            except Exception:
                continue
            if not cat: cat = "Uncategorized"
            if code in inventory:
                inventory[code]["quantity"] += qty
            else:
                inventory[code] = {"category": cat, "name": name or code, "quantity": qty, "price": unit_price}
            append_profit_loss(now, cat, name or code, -qty, unit_price, unit_price, gst_collected=0.0, status="RETURN")
            returned += 1
        save_inventory()
        update_accounting()
        refresh_summary()
        messagebox.showinfo("Returned", f"Returned {returned} line(s) to inventory.")
        load_receipt()

    def return_all():
        ids = tree.get_children()
        if not ids:
            messagebox.showerror("Error","No items to return.")
            return
        tree.selection_set(ids)
        return_selected()

    btnf = tk.Frame(w, bg=BG_COLOR)
    btnf.pack(fill="x", padx=12, pady=8)
    ttk.Button(btnf, text="Return Selected Line(s)", command=return_selected).pack(side="left", padx=6)
    ttk.Button(btnf, text="Return All", command=return_all).pack(side="left", padx=6)
    ttk.Button(btnf, text="Open Receipts Folder", command=open_receipts_folder).pack(side="right", padx=6)

def open_accounting_window():
    update_accounting()
    if not os.path.exists(ACCOUNTING_FILE):
        messagebox.showinfo("Accounting","No accounting data found.")
        return
    w = tk.Toplevel(root)
    w.title("Accounting")
    w.geometry("760x520")
    w.configure(bg=BG_COLOR)
    tree = ttk.Treeview(w, columns=("Category","Item","Qty","UnitPrice","Total"), show="headings")
    for c in ("Category","Item","Qty","UnitPrice","Total"):
        tree.heading(c, text=c)
        tree.column(c, anchor="center", width=140)
    tree.pack(fill="both", expand=True, padx=10, pady=10)
    with open(ACCOUNTING_FILE, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row: continue
            if row[0].startswith("TOTAL"):
                ttk.Label(w, text=" ".join(row), background=BG_COLOR, font=("Georgia",10,"bold")).pack(pady=6)
                continue
            if len(row) == 5 and row[0] != "Category":
                tree.insert("", "end", values=(row[0], row[1], row[2], f"₹{row[3]}", f"₹{row[4]}"))

def open_profit_loss_window():
    if not os.path.exists(PROFIT_LOSS_FILE):
        messagebox.showinfo("Profit/Loss","No profit/loss data yet.")
        return
    w = tk.Toplevel(root)
    w.title("Profit & Loss")
    w.geometry("980x520")
    w.configure(bg=BG_COLOR)
    cols = ("DateTime","Category","Item","Qty","Cost","Sell","Diff","Total","GST","Status")
    tree = ttk.Treeview(w, columns=cols, show="headings")
    for c in cols:
        tree.heading(c, text=c)
        tree.column(c, anchor="center", width=100)
    tree.pack(fill="both", expand=True, padx=8, pady=8)
    total_profit = 0.0
    total_loss = 0.0
    with open(PROFIT_LOSS_FILE, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        rows = list(reader)
        for row in rows[1:]:
            if not row or len(row) < 10:
                continue
            dt, cat, item, qty, cost, sell, diff, total, gst_col, status = row[:10]
            tree.insert("", "end", values=(dt,cat,item,qty,f"₹{cost}",f"₹{sell}",f"₹{diff}",f"₹{total}",f"₹{gst_col}",status))
            try:
                if status == "PROFIT":
                    total_profit += float(total)
                elif status == "LOSS":
                    total_loss += abs(float(total))
            except:
                pass
    ttk.Label(w, text=f"TOTAL PROFIT: ₹{total_profit:.2f}    TOTAL LOSS: ₹{total_loss:.2f}", background=BG_COLOR, font=("Georgia",11,"bold")).pack(pady=6)

def save_and_exit():
    try:
        save_inventory()
    except:
        pass
    try:
        update_accounting()
    except:
        pass
    root.destroy()

# ----------------------------
# Main control buttons (left panel)
# ----------------------------
b_add = make_button(controls, " Add Item", add_item_gui)
b_add.pack(pady=6)
b_view = make_button(controls, " View Inventory", view_inventory_window)
b_view.pack(pady=6)
b_bill = make_button(controls, " Billing", open_billing_window)
b_bill.pack(pady=6)
b_return = make_button(controls, " Return Item", open_return_window)
b_return.pack(pady=6)
b_account = make_button(controls, " View Accounting", open_accounting_window)
b_account.pack(pady=6)
b_pl = make_button(controls, " Profit/Loss", open_profit_loss_window)
b_pl.pack(pady=6)
b_receipts = make_button(controls, " Receipts Folder", open_receipts_folder)
b_receipts.pack(pady=6)
b_exit = make_button(controls, " Save & Exit", save_and_exit)
b_exit.pack(pady=6)

# Footer
footer = tk.Label(root, text=f"© {STORE_NAME} 2025", bg=BG_COLOR, font=("Georgia",10), fg=TEXT)
footer.pack(side="bottom", pady=8)

# Start app
root.mainloop()


