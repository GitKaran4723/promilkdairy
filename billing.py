# billing.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from flask_login import login_required, current_user
from models import db, Transaction, Bill, Customer, RateChart, MilkType
from utils import week_range_for_date, datetime_start_of, datetime_end_of
from datetime import date, datetime
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from sqlalchemy import func

billing = Blueprint("billing", __name__, url_prefix="")

@billing.route("/bills")
@login_required
def bills_list():
    # admin view of bills
    bills = Bill.query.order_by(Bill.generated_date.desc()).all()
    return render_template("bills.html", bills=bills)

@billing.route("/bills/generate", methods=["POST"])
@login_required
def generate_bills_for_range():
    # POST with start_date and end_date for batch generation, admin only
    if current_user.role != "admin":
        flash("Not authorized", "error")
        return redirect(url_for("dashboard"))
    s = request.form.get("start_date")
    e = request.form.get("end_date")
    if not s or not e:
        flash("Select start and end dates", "error")
        return redirect(url_for("billing.bills_list"))
    start = datetime.strptime(s, "%Y-%m-%d").date()
    end = datetime.strptime(e, "%Y-%m-%d").date()
    customers = Customer.query.all()
    for c in customers:
        txns = Transaction.query.filter(
            Transaction.customer_id == c.id,
            Transaction.date_time >= datetime_start_of(start),
            Transaction.date_time <= datetime_end_of(end)
        ).all()
        if not txns:
            continue
        total = sum(t.total_amount for t in txns)
        existing = Bill.query.filter_by(customer_id=c.id, week_start=start, week_end=end).first()
        if existing:
            existing.total_amount = total
            existing.generated_date = datetime.utcnow()
        else:
            b = Bill(customer_id=c.id, week_start=start, week_end=end, total_amount=total)
            db.session.add(b)
    db.session.commit()
    flash("Bills generated/updated", "success")
    return redirect(url_for("billing.bills_list"))

@billing.route("/bill/<int:bill_id>")
@login_required
def bill_detail(bill_id):
    bill = Bill.query.get_or_404(bill_id)
    # restrict access to admin or bill owner
    if current_user.role == "customer" and current_user.customer_id != bill.customer_id:
        flash("Not authorized", "error")
        return redirect(url_for("dashboard"))
    txns = Transaction.query.filter(Transaction.customer_id == bill.customer_id,
                                    Transaction.date_time >= datetime_start_of(bill.week_start),
                                    Transaction.date_time <= datetime_end_of(bill.week_end)
                                    ).order_by(Transaction.date_time).all()
    # aggregate daily breakdown
    daily = {}
    for t in txns:
        day = t.date_time.date()
        daily.setdefault(day, []).append(t)
    # sorted days
    days = sorted(daily.items(), key=lambda x: x[0])
    return render_template("bill_detail.html", bill=bill, days=days)

@billing.route("/bill/<int:bill_id>/pdf")
@login_required
def bill_pdf(bill_id):
    bill = Bill.query.get_or_404(bill_id)
    if current_user.role == "customer" and current_user.customer_id != bill.customer_id:
        flash("Not authorized", "error")
        return redirect(url_for("dashboard"))

    txns = Transaction.query.filter(
        Transaction.customer_id == bill.customer_id,
        Transaction.date_time >= datetime_start_of(bill.week_start),
        Transaction.date_time <= datetime_end_of(bill.week_end)
    ).order_by(Transaction.date_time).all()

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    margin = 15 * mm
    usable_width = width - 2 * margin

    # Company header
    y = height - margin
    c.setFillColorRGB(0.1, 0.3, 0.6)
    c.setFont("Helvetica-Bold", 20)
    c.drawCentredString(width / 2, y, "MILK DIARY PRIVATE LIMITED")
    y -= 10 * mm

    # Stylish separator
    c.setStrokeColorRGB(0.1, 0.3, 0.6)
    c.setLineWidth(1.5)
    c.line(margin, y, width - margin, y)
    y -= 8 * mm

    # Bill Info
    c.setFont("Helvetica-Bold", 12)
    c.setFillColorRGB(0, 0, 0)
    c.drawString(margin, y, f"Bill for: {bill.customer.name}")
    y -= 6 * mm
    c.setFont("Helvetica", 10)
    c.drawString(margin, y, f"Period: {bill.week_start} to {bill.week_end}")
    y -= 5 * mm
    c.drawString(margin, y, f"Generated on: {bill.generated_date.strftime('%Y-%m-%d %H:%M')}")
    y -= 10 * mm

    # Table header
    col_headers = ["Date", "Session", "Milk", "Qty(L)", "Fat", "Rate", "Amount"]
    col_widths = [0.18, 0.12, 0.18, 0.10, 0.08, 0.12, 0.22]  # relative proportions
    col_positions = [margin]
    for w in col_widths:
        col_positions.append(col_positions[-1] + w * usable_width)


    c.setFont("Helvetica-Bold", 9)
    c.setFillColorRGB(0.95, 0.95, 1)
    c.rect(margin, y - 3, usable_width, 10, fill=1, stroke=0)
    c.setFillColorRGB(0, 0, 0)

    for i, h in enumerate(col_headers):
        c.drawString(col_positions[i] + 2, y, h)
    y -= 12

    # Rows
    c.setFont("Helvetica", 9)
    total = 0
    row_alt = False
    for t in txns:
        if y < margin + 40:  # New page if needed
            c.showPage()
            y = height - margin
        # Alternate row shading
        if row_alt:
            c.setFillColorRGB(0.98, 0.98, 0.98)
            c.rect(margin, y - 2, usable_width, 10, fill=1, stroke=0)
        c.setFillColorRGB(0, 0, 0)

        values = [
            t.date_time.strftime("%d-%m-%Y"),
            t.session,
            t.milk_type.name if t.milk_type else "",
            f"{t.qty_liters:.2f}",
            str(t.fat_value or "-"),
            f"{t.rate_applied:.2f}",
            f"{t.total_amount:.2f}"
        ]
        for i, v in enumerate(values):
            if i >= 3:  # right align for numeric
                c.drawRightString(col_positions[i+1] - 2, y, v)
            else:
                c.drawString(col_positions[i] + 2, y, v)
        y -= 12
        total += t.total_amount
        row_alt = not row_alt

    # Total line
    y -= 5
    c.setStrokeColorRGB(0.1, 0.3, 0.6)
    c.line(margin, y, width - margin, y)
    y -= 12
    c.setFont("Helvetica-Bold", 11)
    c.setFillColorRGB(0.1, 0.3, 0.6)
    c.drawRightString(width - margin, y, f"Total: ₹{total:.2f}")

    # Footer
    y = margin
    c.setFont("Helvetica-Oblique", 9)
    c.setFillColorRGB(0.4, 0.4, 0.4)
    c.drawCentredString(width / 2, y, "Thank you for choosing Milk Diary Pvt Ltd.")
    y -= 12
    c.setFillColorRGB(0.2, 0.2, 0.2)
    c.setFont("Helvetica", 8)
    c.drawCentredString(width / 2, y, "Developed & Maintained by Dhiyug Solutions")

    c.showPage()
    c.save()
    buffer.seek(0)
    filename = f"bill_{bill.customer.name}_{bill.week_start}_{bill.week_end}.pdf"
    return send_file(buffer, as_attachment=True, download_name=filename, mimetype="application/pdf")

@billing.route("/generate-inline-bill", methods=["GET", "POST"])
@login_required
def generate_inline_bill():
    # allow admin to pick customer and date range and create & show bill
    if current_user.role != "admin":
        flash("Not authorized", "error")
        return redirect(url_for("dashboard"))
    customers = Customer.query.all()
    if request.method == "POST":
        cid = int(request.form.get("customer_id"))
        s = request.form.get("start_date")
        e = request.form.get("end_date")
        if not s or not e:
            flash("Select start and end dates", "error")
            return redirect(url_for("generate_inline_bill"))
        start = datetime.strptime(s, "%Y-%m-%d").date()
        end = datetime.strptime(e, "%Y-%m-%d").date()
        txns = Transaction.query.filter(
            Transaction.customer_id == cid,
            Transaction.date_time >= datetime_start_of(start),
            Transaction.date_time <= datetime_end_of(end)
        ).order_by(Transaction.date_time).all()
        total = sum(t.total_amount for t in txns)
        # show summary & option to save as Bill
        return render_template("bill_detail.html",
                               bill=None,
                               days=group_transactions_by_day(txns),
                               inline_total=total,
                               start=start, end=end, cust=Customer.query.get(cid))
    return render_template("generate_bill.html", customers=customers)

def group_transactions_by_day(txns):
    daily = {}
    for t in txns:
        day = t.date_time.date()
        daily.setdefault(day, []).append(t)
    return sorted(daily.items(), key=lambda x: x[0])

@billing.route("/customer/portal")
@login_required
def customer_portal():
    # customer view of their transactions / pending balance
    if current_user.role != "customer":
        flash("This page is for customers only", "error")
        return redirect(url_for("dashboard"))
    c = Customer.query.get(current_user.customer_id)
    txns = Transaction.query.filter(Transaction.customer_id == c.id).order_by(Transaction.date_time.desc()).limit(200).all()
    # compute outstanding: for simplicity, sum of Sell (we owe customer) - Purchase (customer owes firm)
    owed = sum(t.total_amount for t in Transaction.query.filter(Transaction.customer_id==c.id, Transaction.txn_type=="Sell"))
    owes = sum(t.total_amount for t in Transaction.query.filter(Transaction.customer_id==c.id, Transaction.txn_type=="Purchase"))
    net = owed - owes
    return render_template("customer_portal.html", customer=c, txns=txns, net=net)
