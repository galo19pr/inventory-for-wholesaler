from flask import Flask, render_template, request, redirect, session, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = "super_secret_key_change_this"  # Required for login & sessions
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///wholesaler.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- DATABASE MODELS ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(50))  # In production, use hashing!

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    batch_number = db.Column(db.String(50), nullable=False)
    expiry_date = db.Column(db.Date, nullable=False)
    quantity = db.Column(db.Integer, default=0)
    unit_price = db.Column(db.Float, default=0.0)
    unit = db.Column(db.String(20))

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_name = db.Column(db.String(100))
    action_type = db.Column(db.String(10)) # 'IN' or 'OUT'
    qty = db.Column(db.Integer)
    date = db.Column(db.DateTime, default=datetime.utcnow)

# Create Database & Default Admin
with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        db.session.add(User(username='admin', password='password123'))
        db.session.commit()

# --- AUTHENTICATION ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username, password=password).first()
        if user:
            session['user'] = user.username
            return redirect(url_for('monitor'))
        else:
            flash('Invalid credentials!')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

# --- ROUTES ---
@app.route('/')
def monitor():
    if 'user' not in session: return redirect(url_for('login'))
    
    # Alerts
    low_stock = Product.query.filter(Product.quantity < 50).all()
    six_months = datetime.now().date() + timedelta(days=180)
    expiring = Product.query.filter(Product.expiry_date <= six_months).all()
    
    # Trends (Top 5 Sold)
    trends = db.session.query(Transaction.product_name, db.func.sum(Transaction.qty).label('total'))\
        .filter(Transaction.action_type=='OUT').group_by(Transaction.product_name)\
        .order_by(db.desc('total')).limit(5).all()
        
    return render_template('monitor.html', low_stock=low_stock, expiring=expiring, trends=trends)

@app.route('/inventory')
def inventory():
    if 'user' not in session: return redirect(url_for('login'))
    
    search = request.args.get('search', '')
    if search:
        items = Product.query.filter(Product.name.contains(search) | Product.batch_number.contains(search)).all()
    else:
        items = Product.query.all()
    
    total_val = sum(i.quantity * i.unit_price for i in items)
    cart = session.get('cart', [])
    return render_template('inventory.html', items=items, total_val=total_val, cart=cart, search=search)

@app.route('/report')
def report():
    if 'user' not in session: return redirect(url_for('login'))
    transactions = Transaction.query.order_by(Transaction.date.desc()).all()
    return render_template('report.html', transactions=transactions)

# --- ACTIONS ---
@app.route('/register', methods=['POST'])
def register():
    try:
        new_prod = Product(
            name=request.form['name'],
            batch_number=request.form['batch_number'],
            expiry_date=datetime.strptime(request.form['expiry_date'], '%Y-%m-%d').date(),
            quantity=int(request.form['quantity']),
            unit_price=float(request.form['unit_price']),
            unit=request.form['unit']
        )
        db.session.add(new_prod)
        db.session.add(Transaction(product_name=new_prod.name, action_type='IN', qty=new_prod.quantity))
        db.session.commit()
    except Exception as e:
        flash(f"Error: {e}")
    return redirect(url_for('inventory'))

@app.route('/delete/<int:id>')
def delete(id):
    if 'user' not in session: return redirect(url_for('login'))
    
    # Find the item by its ID
    item_to_delete = Product.query.get_or_404(id)

    try:
        db.session.delete(item_to_delete)
        db.session.commit()
        flash("Item deleted successfully!")
        return redirect('/inventory') # Redirect back to the inventory page
    except Exception as e:
        db.session.rollback()
        return f"There was a problem deleting that item: {e}"

@app.route('/add_to_cart/<int:id>')
def add_to_cart(id):
    product = Product.query.get(id)
    if product:
        cart = session.get('cart', [])
        cart.append({'id': product.id, 'name': product.name, 'price': product.unit_price})
        session['cart'] = cart
        session.modified = True
    return redirect(url_for('inventory'))

@app.route('/checkout', methods=['POST'])
def checkout():
    cart = session.get('cart', [])
    if not cart: return redirect(url_for('inventory'))
    
    for item in cart:
        prod = Product.query.get(item['id'])
        if prod and prod.quantity > 0:
            prod.quantity -= 1
            db.session.add(Transaction(product_name=prod.name, action_type='OUT', qty=1))
    
    db.session.commit()
    session.pop('cart', None)
    flash("Sale Completed Successfully!")
    return redirect(url_for('inventory'))

@app.route('/clear_cart')
def clear_cart():
    session.pop('cart', None)
    return redirect(url_for('inventory'))

if __name__ == '__main__':
    app.run(debug=True)