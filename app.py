from flask import Flask, request, render_template, redirect, url_for, session, jsonify, send_file
from flask_socketio import SocketIO, emit
from pymongo import MongoClient
from bson.objectid import ObjectId
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from io import BytesIO
from pymongo.errors import ConnectionFailure
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os
from datetime import datetime
import random
import string
#https://50cd-220-158-183-14.ngrok-free.app

font_path = os.path.join('/Users/samarthgayakhe/Documents/_software_project_', 'NotoSans-Italic-VariableFont_wdth,wght.ttf')
pdfmetrics.registerFont(TTFont('NotoSans', font_path))

app = Flask(__name__)
app.secret_key = 'your_secret_key'
socketio = SocketIO(app)


connection_string = "mongodb://localhost:27017/"

try:
    # Create a MongoClient instance
    client = MongoClient(connection_string)

    # The command is used to check if the server is available
    client.admin.command('ping')
    print("Connected to MongoDB successfully!")

except ConnectionFailure as e:
    print(f"Failed to connect to MongoDB: {e}")

db = client['Software_Proj']
user_collection = db['users']
table_collection = db['tables']
order_collection = db['orders']
menu_collection = db['menu']
kitchen_collection = db['kitchen_orders']
table_order_collection = db['table_orders']

@app.route('/', methods=['GET'])
def default():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET'])
def login_form():
    error = request.args.get('error')
    return render_template('login.html', error=error)

@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username')
    password = request.form.get('password')

    user = user_collection.find_one({"username": username})
    if user and user['password'] == password:
        session['username'] = username
        session['access'] = user['access']
        return redirect(url_for(user['access']))
    else:
        return redirect(url_for('login_form', error='Invalid login, please try again.'))

@app.route('/admin', methods=['GET'])
def admin():
    if 'username' in session and session['access'] == 'admin':
        # Convert MongoDB cursors to lists and remove ObjectId fields
        users = list(user_collection.find({}, {'_id': 0}))
        tables = list(table_collection.find({}, {'_id': 0}))
        available_tables = list(table_collection.find({"status": "available"}, {'_id': 0}))
        
        return render_template('admin.html', 
                             users=users,
                             tables=tables, 
                             available_tables=available_tables)
    else:
        return redirect(url_for('login_form', error='Unauthorized access.'))

@app.route('/register_user', methods=['POST'])
def register_user():
    if 'username' in session and session['access'] == 'admin':
        username = request.form.get('username')
        password = request.form.get('password')
        access = request.form.get('access')

        if user_collection.find_one({"username": username}):
            return jsonify({'status': 'error', 'message': 'Username already exists.'})

        user_collection.insert_one({"username": username, "password": password, "access": access})
        
        # Fetch updated user list
        users = list(user_collection.find({}, {'_id': 0}))
        
        # Emit update to all connected clients
        socketio.emit('users_updated', {'users': users})
        
        return jsonify({'status': 'success', 'message': 'User registered successfully.'})
    else:
        return jsonify({'status': 'error', 'message': 'Unauthorized access.'})

@app.route('/delete_user', methods=['POST'])
def delete_user():
    if 'username' in session and session['access'] == 'admin':
        username = request.form.get('username')

        if user_collection.find_one({"username": username}):
            user_collection.delete_one({"username": username})
            
            # Fetch updated user list
            users = list(user_collection.find({}, {'_id': 0}))
            
            # Emit update to all connected clients
            socketio.emit('users_updated', {'users': users})
            
            return jsonify({'status': 'success', 'message': 'User deleted successfully.'})
        else:
            return jsonify({'status': 'error', 'message': 'User not found.'})
    else:
        return jsonify({'status': 'error', 'message': 'Unauthorized access.'})

@app.route('/delete_user/<string:username>', methods=['DELETE'])
def deleteuser(username):
    if 'username' in session and session['access'] == 'admin':
        user = user_collection.find_one({"username": username})
        if user:
            user_collection.delete_one({"username": username})
            users = list(user_collection.find({}, {'_id': 0}))
            socketio.emit('users_updated', {'users': users})
            return jsonify({'status': 'success', 'message': 'User deleted successfully.'})
        else:
            return jsonify({"error": "User not found"}), 404
    else:
        return jsonify({"error": "Unauthorized access"}), 403

@app.route('/vacate_table/<string:table_number>', methods = ['DELETE'])
def vacate_table(table_number):
    if 'username' in session:
        table = table_collection.find_one({"table_number": table_number})   
        if table:
            table_collection.update_one(
                {"table_number": table_number},
                {"$set": {"status": "available", "customer_name": ""}}
            )
            order_collection.delete_one({"Table": table_number})
            table_order_collection.delete_many({"table_number": table_number})
            tables = list(table_collection.find({}, {'_id': 0}))
            socketio.emit('tables_updated', {'tables': tables})
            return jsonify({'status': 'success', 'message': 'Table vacated successfully.'})
        else:
            return jsonify({'status': 'error', 'message': 'Table not found.'})  
    else:
        return jsonify({'status': 'error', 'message': 'Unauthorized access.'})

@app.route('/assign_table', methods=['POST'])
def assign_table():
    if 'username' in session and session['access'] == 'admin':
        table_number = request.form.get('table_number')
        customer_name = request.form.get('customer_name')

        table = table_collection.find_one({"table_number": table_number})
        if table:
            table_collection.update_one(
                {"table_number": table_number},
                {"$set": {"status": "occupied", "customer_name": customer_name}}
            )
            
            # Fetch updated table list
            tables = list(table_collection.find({}, {'_id': 0}))
            
            # Emit update to all connected clients
            socketio.emit('tables_updated', {'tables': tables})
            
            return jsonify({'status': 'success', 'message': 'Table assigned successfully.'})
        else:
            return jsonify({'status': 'error', 'message': 'Table not found.'})
    else:
        return jsonify({'status': 'error', 'message': 'Unauthorized access.'})

@app.route('/logout', methods=['GET'])
def logout():
    session.pop('username', None)
    session.pop('access', None)
    return redirect(url_for('login_form'))

@app.route('/waiter', methods=['GET'])
def waiter():
    if 'username' in session:
        # Convert MongoDB cursor to list and remove ObjectId fields
        tables = list(table_collection.find({}, {'_id': 0}))
        return render_template('wait.html', access=session['access'], tables=tables)
    else:
        return redirect(url_for('login_form', error='Please log in first.'))

@app.route('/order', methods=['GET'])
def order():
    if 'username' in session:
        return render_template('order.html', access=session['access'])
    else:
        return redirect(url_for('login_form', error='Please log in first.'))

@app.route('/get_orders/<string:table_number>', methods=['GET'])
def get_orders(table_number):
    try:
        # Find orders with the specified table_number
        orders = list(table_order_collection.find({"table_number": table_number}, {"_id": 0, "items": 1, "status": 1}))
        return jsonify(orders)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Socket event handler for real-time order updates
@socketio.on('order_update')
def handle_order_update(data):
    if 'username' in session and session.get('access') == 'waiter':
        table_number = data['table_number']
        table = table_order_collection.find_one({"table_number": table_number}, {"_id": 0, "items": 1, "status": 1})
        if table:
            # Emit the updated order details to all connected clients
            socketio.emit('orders_updated', {
                'table_number': table_number,
                'items': table.get('items', []),
                'status': table.get('status')
            })


@app.route('/api/menu')
def get_menu_items():
    menu_items = db["menu"].find()
    items = [{"name": item["name"], "price": item["price"], "description": item["description"], "category": item["category"]} for item in menu_items]
    return jsonify(items)

@app.route('/checkout', methods=['POST'])
def checkout():
    order_data = request.json
    if not order_data or 'items' not in order_data or not isinstance(order_data['items'], list):
        return jsonify({"error": "Invalid order data"}), 400

    table_number = order_data['table_number']
    update_kitchen(order_data)
    # Check if an order for this table already exists
    existing_order = order_collection.find_one({"Table": table_number})
    
    if existing_order:
        # If an order exists, update quantities or add new items
        for new_item in order_data['items']:
            item_name = new_item['name']
            item_quantity = new_item['quantity']
            
            # Check if the item already exists in the order
            item_exists = False
            for existing_item in existing_order['items']:
                if existing_item['name'] == item_name:
                    # Update the quantity
                    order_collection.update_one(
                        {"Table": table_number, "items.name": item_name},
                        {"$inc": {"items.$.quantity": item_quantity}}
                    )
                    item_exists = True
                    break
            
            if not item_exists:
                # If the item doesn't exist, add it to the order
                order_collection.update_one(
                    {"Table": table_number},
                    {"$push": {"items": new_item}}
                )
    else:
        # If no order exists, create a new one
        order = {"items": order_data['items'], "Table": table_number,"status": "preparing"}
        order_collection.insert_one(order)
    
    # Fetch the updated order to send back to the client
    updated_order = order_collection.find_one({"Table": table_number})
    
    # Emit a socket event to notify clients of the update
    socketio.emit('orders_updated', {
        'table_number': table_number,
        'orders': updated_order['items']
    })
    
    return jsonify({"message": "Order updated successfully", "order": updated_order['items']}), 200

@app.route('/menu', methods=['GET'])
def menu():
    return render_template('menu.html')

@app.route('/generate_invoice/<string:table_number>', methods=['GET'])
def generate_invoice(table_number):

    order = order_collection.find_one({"Table": table_number})
    if not order:
        return jsonify({"error": "No order found for this table"}), 404
    print(order)
    # Create a BytesIO buffer to receive PDF data
    buffer = BytesIO()

    # Create the PDF object, using the BytesIO object as its "file."
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []

    # Add title
    styles = getSampleStyleSheet()
    elements.append(Paragraph(f"Invoice for Table {table_number}", styles['Title']))

    # Create table data
    data = [['Item', 'Quantity', 'Price', 'Total']]
    total_amount = 0
    for item in order['items']:
        price = menu_collection.find_one({"name": item['name']})['price']
        item_total = int(item['quantity']) * int(price)
        data.append([item['name'], str(item['quantity']), price, item_total])
        total_amount += int(item_total)
    sgst = total_amount * 0.09
    cgst = total_amount * 0.09

    data.append(['', '', 'SGST (9%):', f"₹{sgst:.2f}"])
    data.append(['', '', 'CGST (9%):', f"₹{cgst:.2f}"])
    total_amount += sgst + cgst

    # Add total row
    data.append(['', '', 'Total:', f"₹{total_amount:.2f}"])

    # Create table
    table = Table(data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, -1), 'NotoSans'),  # Use registered font for all cells
        ('FONTSIZE', (0, 0), (-1, 0), 14),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, -3), (-1, -1), colors.beige),  # Background for tax and total rows
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('ALIGN', (-2, -3), (-1, -1), 'RIGHT'),  # Right align last two columns of tax and total rows
        ('ALIGN', (-2, 1), (-2, -4), 'CENTER'),  # Center align the rest of the price column
        ('FONTSIZE', (0, 1), (-1, -1), 12),  # Regular text size for content
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))

    elements.append(table)

    # Build PDF
    doc.build(elements)

    # Move to the beginning of the StringIO buffer
    buffer.seek(0)

    # Send the PDF as a file download
    return send_file(buffer, as_attachment=False, download_name=f'invoice_table_{table_number}.pdf', mimetype='application/pdf')

@app.route('/get_total_amount/<string:table_number>', methods=['GET'])
def get_total_amount(table_number):
    order = order_collection.find_one({"Table": table_number})
    if not order:
        return jsonify({"error": "No order found for this table"}), 404
    total_amount = 0
    for item in order['items']:
        price = menu_collection.find_one({"name": item['name']})['price']
        item_total = int(item['quantity']) * int(price)
        total_amount += int(item_total)
    total_amount = total_amount + total_amount * 0.18
    return jsonify({'totalAmount': total_amount})

@app.route('/kitchen')
def kitchen():
    return render_template('kitchen.html')

@app.route('/get_kitchen_orders', methods=['GET'])
def get_kitchen_orders():
    try:
        # Get all active orders
        orders = list(kitchen_collection.find({}, {'items.name': 1, 'items.quantity': 1}))
        for order in orders:
            order['_id'] = str(order['_id'])  # Convert ObjectId to string
        return jsonify(orders)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/delete_kitchen_card/<order_id>', methods=['DELETE'])
def delete_kitchen_card(order_id):
    try:
        result = kitchen_collection.delete_one({"_id": ObjectId(order_id)})
        if result.deleted_count > 0:
            # Emit update event after successful deletion
            table_order_collection.update_one({"_id": ObjectId(order_id)}, {"$set": {"status": "ready"}})
            emit_kitchen_update()
            return jsonify({"message": "Order deleted successfully"})
        else:
            return jsonify({"error": "Order not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def emit_kitchen_update():
    """Helper function to emit updated orders to all connected clients"""
    try:
        orders = list(kitchen_collection.find({}, {'items.name': 1, 'items.quantity': 1}))
        for order in orders:
            order['_id'] = str(order['_id'])
        socketio.emit('kitchen_orders_update', orders)
    except Exception as e:
        print(f"Error emitting kitchen update: {e}")

def update_kitchen(order_data):
    """Function to add new order to kitchen"""
    try:
        order = {
            "items": order_data['items'],
            "status": "preparing",
            "table_number": order_data['table_number']
        }
        result = kitchen_collection.insert_one(order)
        if result.inserted_id:
            # Emit update event after successful insertion
            emit_kitchen_update()
            table_order_collection.insert_one(order)
            return {"success": True, "message": "Order added to kitchen"}
        return {"success": False, "message": "Failed to add order"}
    except Exception as e:
        return {"success": False, "message": str(e)}
if __name__ == '__main__':
    socketio.run(app, debug=True)