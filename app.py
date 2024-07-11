import os, random
from models import *
from utils import *
from flask_caching import Cache
from flask_migrate import Migrate
from flask import abort, flash, Flask, Response, render_template, jsonify, redirect, url_for, current_app,request
from sqlalchemy.sql import func
from uuid import uuid4
import string
import bleach
import json
from flask_login import LoginManager, login_user, logout_user, login_required
from concurrent.futures import ThreadPoolExecutor

MAINTENANCE_MODE = False

app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///pages.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.secret_key = 'SUPERRICKPICKLEMEGADONGER'  # Set a secret key for session management
app.config['CACHE_TYPE'] = 'simple'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///pages.db'
db.init_app(app)
cache = Cache()
cache.init_app(app)
openai.api_key = ""
migrate = Migrate(app, db, compare_type=True)

# Assuming 'app' is your Flask app variable
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
# Initialize login manager
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Block IP addresses in the ban list before processing any request
@app.before_request
def block_method():
    ip = request.environ.get('REMOTE_ADDR')
    if ip in ip_ban_list:
        abort(403)

# Check for maintenance mode and render maintenance page if enabled
@app.before_request
def check_for_maintenance():
    if MAINTENANCE_MODE:
        return render_template('maintenance.html'), 503

# Route to award a random item if in debug mode
@app.route('/dev/gain-item')
@login_required
def doitnow():
    if app.debug:
        award_random_item(current_user.id, "POOP", "rare")
        return jsonify({'message': 'item gained'})
    return jsonify({'message': 'route not available while debug mode is off'})

# Render inventory page and combine fragments for the current user
@app.route('/inventory')
@login_required
def render_inv_page():
    combine_fragments(current_user.id)
    return render_template('inventory.html')

# Clear all alerts for the current user
@app.route('/clear-alerts', methods=['POST'])
@login_required
def clear_alerts():
    Alert.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()
    return jsonify({'message': 'All alerts cleared successfully.'})

# Preserve an item for the current user if conditions are met
@app.route('/inventory/preserve/<int:item_id>', methods=['POST'])
@login_required
def preserve_item(item_id):
    item = InventoryItem.query.get(item_id)
    if not item or item.user_id != current_user.id or item.type == 'ingredient' or item.name == 'The busty bun toaster':
        return jsonify({'success': False, 'message': 'This item cannot be preserved.'}), 400
    item.is_preserved = True
    db.session.commit()
    return jsonify({'success': True, 'message': 'Item preserved successfully.'})

# Unpreserve an item for the current user if it exists
@app.route('/inventory/unpreserve/<int:item_id>', methods=['POST'])
@login_required
def unpreserve_item(item_id):
    item = InventoryItem.query.filter_by(id=item_id, user_id=current_user.id).first()
    if not item:
        return jsonify({'success': False, 'message': 'Item not found.'}), 404
    item.is_preserved = False
    db.session.commit()
    return jsonify({'success': True, 'message': 'Item unpreserved successfully.'})

@app.route('/api/inventory', methods=['GET'])
@login_required
def load_inventory():
    # Fetch inventory items, active effects, and items for sale for the current user
    inventory_items = InventoryItem.query.filter_by(user_id=current_user.id).all()
    active_effects = Effect.query.filter(Effect.user_id == current_user.id, Effect.expires_at > datetime.utcnow()).all()
    items_for_sale = ForSaleItem.query.filter_by(seller_id=current_user.id).all()

    # Define sorting orders for types and rarities
    type_order = {'ingredient': 1, 'consumable': 2, 'collectible': 3}
    rarity_order = {'mystical': 1, 'legendary': 2, 'rare': 3, 'common': 4}

    # Custom sort function for inventory items
    def custom_sort(item):
        return (type_order[item['type']], rarity_order[item['rarity']], -item['quality'])

    # Extract IDs of items for sale to exclude from general inventory
    items_for_sale_inventory_item_ids = [item.id for item in items_for_sale]

    # Prepare data for user's loot boxes
    user_loot_boxes_data = [{'id': box.id, 'rarity': box.rarity, 'theme': box.theme} for box in LootBox.query.filter_by(user_id=current_user.id).all()]

    # Prepare data for items for sale
    items_for_sale_data = [{'id': item.id, 'name': item.name, 'description': item.description, 'price_in_seeds': item.price_in_seeds, 'quality': item.quality, 'type': item.type, 'rarity': item.rarity, 'is_preserved': item.is_preserved} for item in items_for_sale]

    # Prepare data for inventory items excluding items for sale
    items_data = [{'id': item.id, 'name': item.name, 'description': item.description, 'rarity': item.rarity, 'type': item.type, 'quality': item.quality, "is_preserved": item.is_preserved} for item in inventory_items if item.id not in items_for_sale_inventory_item_ids]

    # Sort inventory items using the custom sort function
    items_data = sorted(items_data, key=custom_sort)

    # Prepare data for active effects, including remaining time until they expire
    effects_data = [{'id': effect.id, 'effect_name': effect.effect_name, 'expires_in': str(effect.expires_at - datetime.utcnow())} for effect in active_effects]

    # Return JSON response containing all relevant data
    return jsonify({
        'inventory_items': items_data,
        'active_effects': effects_data,
        'items_for_sale': items_for_sale_data,
        'user_loot_boxes': user_loot_boxes_data
    })


@app.route('/save/templates', methods=['POST'])
@login_required
def store_template():
    # Check if the user has reached the template limit
    if Template.query.filter_by(user_id=current_user.id).count() >= 10:
        return jsonify({"message": "Template limit reached. You can only save up to 10 templates."}), 403

    # Clean and prepare user input
    data = request.json
    user_input = bleach.clean(data['user_input'], strip=True)
    # Check if user input length is within the allowed prompt length
    max_prompt_length = items_for_purchase['Prompt Length Increase']['prompt_length']['length'] if any(p.item_type == 'Prompt Length Increase' for p in current_user.purchases) else 250

    if len(user_input) > max_prompt_length:
        return jsonify({"message": f"Prompt length exceeded. Maximum allowed characters this may be due to a boost: {max_prompt_length}."}), 400

    # Generate a unique template name based on user input
    if len(user_input) < 30:
        template_name = ''.join(random.choices(string.ascii_letters + string.digits, k=30))
    else:
        template_name = user_input[:10] + ''.join(random.choices(string.ascii_letters + string.digits, k=10)) + user_input[-10:]

    # Create and store the new template
    new_template = Template(
        template_name=template_name,
        user_input=user_input,
        theme=data['theme'],
        visibility=data['visibility'],
        safe=data['safe'],
        mode=data['mode'],
        user_id=current_user.id
    )
    db.session.add(new_template)
    db.session.commit()

    # Return success message with the new template ID
    return jsonify({"message": "Template stored successfully", "template_id": new_template.id}), 201
@app.route('/trade-up', methods=['POST'])
@login_required
def trade_up():
    data = request.json
    item_type = data.get('type')
    if item_type == "common":
        items = InventoryItem.query.filter(InventoryItem.user_id == current_user.id, InventoryItem.type != "ingredient", InventoryItem.rarity == "common", InventoryItem.name != "The busty bun toaster", InventoryItem.is_preserved == False).limit(8).all()
        logging.info("ITEMDATA",items)
        if len(items) < 8:
            return jsonify({"error": "Not enough items for trade up."}), 400
        outcome = choices(["rare", "legendary"], weights=[65, 35], k=1)[0]
    elif item_type == "rare":
        items = InventoryItem.query.filter(InventoryItem.user_id == current_user.id, InventoryItem.type != "ingredient", InventoryItem.rarity == "rare", InventoryItem.name != "The busty bun toaster", InventoryItem.is_preserved == False).limit(3).all()
        if len(items) < 3:
            return jsonify({"error": "Not enough items for trade up."}), 400
        outcome = choices(["legendary", "two_legendary"], weights=[85, 15], k=1)[0]
    elif item_type == "legendary":
        items = InventoryItem.query.filter(InventoryItem.user_id == current_user.id, InventoryItem.type != "ingredient", InventoryItem.rarity == "legendary", InventoryItem.name != "The busty bun toaster", InventoryItem.is_preserved == False).limit(3).all()
        if len(items) < 3:
            return jsonify({"error": "Not enough items for trade up."}), 400
        outcome = choices(["mystical", "nothing"], weights=[50, 50], k=1)[0]
    else:
        return jsonify({"error": "Invalid item type for trade up."}), 400

    if not items:
        return jsonify({"error": "Not enough items for trade up."}), 400

    # Remove used items from user inventory
    for item in items:
        db.session.delete(item)
    db.session.commit()
    user_input = random.choice([page.user_input for page in GeneratedPage.query.filter_by(is_unlisted=False).all()])

    if outcome == "rare":
        rare_item_1 = award_random_item(current_user.id, user_input, rarity="rare")
        return jsonify({"success": True, "outcome": f"Succesfully traded up! You have received a rare. Item received is {rare_item_1.name}"}), 200
    elif outcome == "legendary":
        leg_item_1 = award_random_item(current_user.id, user_input, rarity="legendary")
        return jsonify({"success": True, "outcome": f"Succesfully traded up! You have received a legendary. Item received is {leg_item_1.name}"}), 200
    elif outcome == "two_legendary":
        leg_item_1 = award_random_item(current_user.id, user_input, rarity="legendary")
        leg_item_2 = award_random_item(current_user.id, user_input, rarity="legendary")
        return jsonify({"success": True, "outcome": f"Succesfully traded up! You have received a double legendary. Items received are {leg_item_1.name} and {leg_item_2.name}"}), 200
    elif outcome == "mystical":
        mystical_item = award_random_item(current_user.id, user_input, rarity="mystical")
        return jsonify({"success": True, "outcome": f"Succesfully traded up! You have received a mystical item. Item received is {mystical_item.name}"}), 200
    elif outcome == "nothing":
        return jsonify({"success": True, "outcome": "Unfortunately, you received nothing from the trade-up."}), 200





@app.route('/templates/<int:template_id>', methods=['DELETE'])
@login_required
def delete_template(template_id):
    # Fetch the template with the given template_id
    template = Template.query.get_or_404(template_id)
    # Check if the current user is the owner of the template
    if template.user_id != current_user.id:
        abort(403)  # Only allow deletion by the template owner
    # Delete the template from the database
    db.session.delete(template)
    db.session.commit()
    # Return a success message
    return jsonify({"message": "Template deleted successfully"}), 204

@app.route('/load/templates', methods=['GET'])
@login_required
def load_templates():
    # Fetch all templates belonging to the current user
    templates = Template.query.filter_by(user_id=current_user.id).all()
    # Prepare the data to be returned
    templates_data = [{
        'template_id': template.id,
        'template_name': template.template_name,
        'user_input': template.user_input,
        'theme': template.theme,
        'visibility': template.visibility,
        'safe': template.safe,
        'mode': template.mode,
        'user_id': template.user_id
    } for template in templates]
    # Return the data
    return jsonify(templates_data)
@app.route('/load/templates/<int:template_id>', methods=['GET'])
@login_required
def load_template_by_id(template_id):
    # Query the database for a template with the given template_id belonging to the current user
    template = Template.query.filter_by(id=template_id, user_id=current_user.id).first()

    # If the template is not found, return a 404 error
    if template is None:
        return jsonify({"error": "Template not found"}), 404

    # If the template is found, return its details
    template_details = {
        'template_id': template.id,
        'template_name': template.template_name,
        'user_input': template.user_input,
        'theme': template.theme,
        'visibility': template.visibility,
        'safe': template.safe,
        'mode': template.mode,
        'user_id': template.user_id
    }
    return jsonify(template_details)

@app.route('/challenges')
@login_required  # Ensure only logged-in users can access
def challenge():
    # Count the number of unlisted pages for the current user
    user_unlisted_pages_count = len([page for page in current_user.pages if page.is_unlisted])
    # If the count is greater than or equal to 10, complete the challenge and award a special item
    if user_unlisted_pages_count >= 10:
        complete_challenge(current_user, "The Incognito")
        award_special_item(current_user, "The busty bun toaster")
    # Render the challenges template with the current user's username
    return render_template('challenges.html', current_username=current_user.username)

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    # If the request method is POST, handle the signup process
    if request.method == 'POST':
        # Get the username and password from the request form
        username = request.form.get('username').lower()
        password = request.form.get('password')
        # Check if the username already exists
        user = User.query.filter(func.lower(User.username) == func.lower(username)).first()
        if user:
            # If the username already exists, return an error message
            flash('Username already exists.', 'error')
            return jsonify(success=False, message='Username already exists.')

        # Create a new user with the provided username
        new_user = User(username=username)
        # Set the password for the new user
        new_user.set_password(password)
        # Generate a reset string for the new user
        reset_string = new_user.generate_reset_string()
        # Add the new user to the database
        db.session.add(new_user)
        db.session.commit()

        # Return a JSON response with the success status, reset string, and a message
        return jsonify(success=True, reset_string=reset_string, message='Signup successful. Please save your reset string securely.')

    # If the request method is not POST, render the signup template
    return render_template('signup.html')

@app.route('/like_page/<uuid>', methods=['POST'])
@login_required
def like_page(uuid):
    # Fetch the page with the given uuid
    page = GeneratedPage.query.filter_by(uuid=uuid).first_or_404()
    # Check if the current user has already liked the page
    existing_like = PageLike.query.filter_by(page_id=page.id, user_id=current_user.id).first()

    # If the user has already liked the page, remove the like
    if existing_like:
        db.session.delete(existing_like)
    # If the user has not liked the page, add a new like
    else:
        new_like = PageLike(page_id=page.id, user_id=current_user.id)
        db.session.add(new_like)
    # Commit the changes to the database
    db.session.commit()
    # Return a JSON response with the success status
    return jsonify(success=True)


@app.route('/open-loot-box/<int:loot_box_id>', methods=['POST'])
@login_required
def open_loot_box(loot_box_id):
    # Fetch the loot box with the given id
    loot_box = LootBox.query.get_or_404(loot_box_id)
    # Check if the loot box belongs to the current user
    if loot_box.user_id != current_user.id:
        return jsonify({"error": "Invalid request"}), 400

    # Log the user who obtained the loot box
    # Define the rarity weights for each loot box rarity
    loot_box_rarity_weights = {
        'common': {'common': 60, 'rare': 25, 'legendary': 10, 'mystical': 5},
        'rare': {'common': 40, 'rare': 30, 'legendary': 20, 'mystical': 10},
        'legendary': {'common':30 , 'rare':30 , 'legendary':25 , 'mystical': 15},
    }

    # Determine the distribution to use based on the loot box's rarity
    rarity_distribution = loot_box_rarity_weights.get(loot_box.rarity, loot_box_rarity_weights['common'])

    # Choose the item rarity based on the determined distribution
    selected_item_rarity = random.choices(list(rarity_distribution.keys()), weights=rarity_distribution.values(), k=1)[0]

    items = [award_random_item(current_user.id, random.choice(list(collections[loot_box.theme])), selected_item_rarity) for _ in range(5)]

    # Delete the loot box from the database
    db.session.delete(loot_box)
    db.session.commit()

    # Return a JSON response with the success status and the names of the obtained items
    return jsonify({"success": True, "items": ", ".join([item.name for item in items])}), 200

@app.route('/shopadd/add-item', methods=['POST'])
def add_item_for_sale():
    # Check if the request method is POST
    if request.method == 'POST':
        # Get the JSON data from the request
        data = request.json
        # If no data is provided, return an error
        print("data",data)
        if not data:
            return jsonify({"message": "No data provided."}), 400

        # Get the item details from the data
        item_id, name, description, price_in_seeds, quality, item_type, rarity = data.get('id'), data.get('name'), data.get('description'), data.get('price_in_seeds'), data.get('quality'), data.get('type'), data.get('rarity')
        # Set the preserved status to True
        is_preserved = True
        # If the item is "The busty bun toaster" and the quality is 100, return an error
        if name == "The busty bun toaster" and int(quality) == 100:
            return jsonify({"message": "This item cannot be sold."}), 403

        # If any of the required fields are missing, return an error
        if not all([name, description, price_in_seeds, quality, item_type, rarity]):
            return jsonify({"message": "All fields are required."}), 400

        # Set the maximum number of listings based on the user's inventory
        max_listings = 10 if InventoryItem.query.filter_by(user_id=current_user.id, name="Stockbrokers powerful powder").first() else 5

        # If the user has reached the maximum number of listings, return an error
        if ForSaleItem.query.filter_by(seller_id=current_user.id).count() >= max_listings:
            return jsonify({"message": "You can only list up to 5 items at a time."}), 403

        # Create a new item for sale
        new_item_for_sale = ForSaleItem(
            seller_id=current_user.id,
            name=name,
            description=description,
            price_in_seeds=price_in_seeds,
            quality=quality,
            type=item_type,
            rarity=rarity,
            is_preserved=True
        )

        # Get the inventory item and delete it
        inventory_item = InventoryItem.query.get_or_404(item_id)
        db.session.delete(inventory_item)
        db.session.commit()
        # Add the new item for sale to the database
        db.session.add(new_item_for_sale)
        db.session.commit()

        # Return a success message
        return jsonify({"message": "Item added for sale successfully."}), 201

@app.route('/shopremove/remove-item/<int:item_id>', methods=['POST'])
@login_required
def cancel_item_sale(item_id):
    # Get the item for sale
    item_for_sale = ForSaleItem.query.get_or_404(item_id)
    # Check if the current user is the seller
    if item_for_sale.seller_id != current_user.id:
        return jsonify({"message": "You do not have the permission to remove this item."}), 403

    # Create a new inventory item
    inventory_item = InventoryItem(
        user_id=current_user.id,
        name=item_for_sale.name,
        description=item_for_sale.description,
        rarity=item_for_sale.rarity,
        type=item_for_sale.type,
        quality=item_for_sale.quality,
        is_preserved=False
    )

    # Add the inventory item back to the user's inventory
    db.session.add(inventory_item)
    # Delete the item for sale
    db.session.delete(item_for_sale)
    db.session.commit()

    # Return a success message
    return jsonify({"message": "Item removed from sale successfully."}), 200



@app.route('/purchase-item/<int:item_id>', methods=['POST'])
@login_required
def purchase_for_sale_item(item_id):
    # Get the item for sale
    item_for_sale = ForSaleItem.query.get_or_404(item_id)
    # Check if the current user has enough sesame seeds to purchase the item
    if current_user.sesame_seeds < item_for_sale.price_in_seeds:
        return jsonify({"message": "Not enough sesame seeds to purchase this item."}), 400

    # Deduct the sesame seeds from the buyer and add them to the seller
    current_user.sesame_seeds -= item_for_sale.price_in_seeds
    seller = User.query.get_or_404(item_for_sale.seller_id)
    seller.sesame_seeds += item_for_sale.price_in_seeds

    # Create a new inventory item for the buyer
    new_inventory_item = InventoryItem(
        user_id=current_user.id,
        name=item_for_sale.name,
        description=item_for_sale.description,
        quality=item_for_sale.quality,
        type=item_for_sale.type,
        rarity=item_for_sale.rarity
    )

    # If the price of the item is greater than or equal to 100, complete the challenge for the seller and award a special item
    if item_for_sale.price_in_seeds >= 100:
        complete_challenge(seller, "The Master Salesman")
        award_special_item(seller,"Stockbrokers powerful powder")

    # Send a message to the seller about the sale
    seller_message = f"Your item '{item_for_sale.name}' has been sold for {item_for_sale.price_in_seeds} sesame seeds."
    add_user_alert(item_for_sale.seller_id, "item_sold", seller_message)

    # Add the new inventory item to the database, delete the item for sale, and commit the changes
    db.session.add(new_inventory_item)
    db.session.delete(item_for_sale)
    db.session.commit()

    # Return a success message
    return jsonify({"message": "Item purchased successfully."}), 200

@app.route('/shop')
def shop():
    # Fetch all items for sale, user listed items, and purchased items
    for_sale_items = ForSaleItem.query.filter(ForSaleItem.seller_id != current_user.id).all()
    for_sale_items_json = [
        {
            'id': item.id,
            'name': item.name,
            'seller_id': User.query.get(item.seller_id).username,
            'description': item.description,
            'price_in_seeds': item.price_in_seeds,
            'quality': item.quality,
            'type': item.type,
            'rarity': item.rarity
        } for item in for_sale_items
    ]
    purchased_items = Purchase.query.filter_by(user_id=current_user.id).all()
    purchased_items_names = {p.item_name for p in purchased_items}

    # Serialize items_for_purchase manually
    items_for_purchase_serialized = {}
    for category, items in items_for_purchase.items():
        items_for_purchase_serialized[category] = {}
        for item_name, item_details in items.items():
            # Ensure all item details are serializable
            items_for_purchase_serialized[category][item_name] = {
                'description': item_details['description'],
                'cost': item_details['cost'],
                'purchased': item_name in purchased_items_names or item_details.get('cost', 0) == 0
            }

    # Check if the user has completed the store spree challenge
    user_purchases_count = Purchase.query.filter_by(user_id=current_user.id).count()
    if user_purchases_count >= 5:
        complete_challenge(current_user, "The Store Spree")

    # Check if the user has completed the eclectic collector challenge
    categories_purchased = {purchase.item_type for purchase in current_user.purchases}
    all_categories = set(items_for_purchase.keys())
    if categories_purchased == all_categories:
        complete_challenge(current_user, "The Eclectic Collector")

    # Render the shop page with the updated details
    return render_template('shop.html', items_for_purchase=items_for_purchase_serialized, for_sale_items=for_sale_items_json, sesame_seeds=current_user.sesame_seeds)
@app.route('/comment_page/<uuid>', methods=['POST'])
@login_required
def comment_page(uuid):
    # Count the number of pages the user has commented on
    user_commented_pages = PageComment.query.filter_by(user_id=current_user.id).distinct(PageComment.page_id).count()
    # If the user has commented on 5 or more pages, complete the challenge
    if user_commented_pages >= 5:
        complete_challenge(current_user, "The Comment Crusader")

    # Fetch the page with the given UUID
    page = GeneratedPage.query.filter_by(uuid=uuid).first_or_404()
    # Get the comment text from the request
    comment_text = request.form.get('comment')

    # Sanitize the comment text using Bleach
    sanitized_comment = bleach.clean(comment_text, strip=True)
    # Fetch all ingredients in the user's inventory
    ingredients = InventoryItem.query.filter_by(user_id=current_user.id, type='ingredient').all()

    # If the comment contains 50 or more words, complete the challenge
    if len(sanitized_comment.split()) >= 50:
        complete_challenge(current_user, "The Creative Commentator")
    # Set the maximum comment length to 150 characters
    max_length = 150
    # If the user has the ingredient "A dash of pepper", increase the maximum comment length to 300 characters

    if len(sanitized_comment) > max_length:
        return jsonify(sucess=False, message=f"Comment can't be more than {max_length} characters")
    # If the comment is not empty, add a new comment to the page
    if sanitized_comment:
        new_comment = PageComment(page_id=page.id, user_id=current_user.id, comment_text=sanitized_comment)
        db.session.add(new_comment)
        # If the user has the ingredient "Burger of the gods", award them 10 sesame seeds
        for ingredient in ingredients:
            if ingredient == "Burger of the gods":
                current_user.sesame_seeds += 15
            elif ingredient == "A dash of pepper":
                max_length = 300
        # Award the user 5 sesame seeds for commenting
        current_user.sesame_seeds += 5
        # Commit the changes to the database
        db.session.commit()
        # Return a success message
        return jsonify(success=True)

    # If the comment is empty, return an error message
    return jsonify(success=False, message="Comment text is required.")

@app.route('/api/completed-challenges/<username>')
@login_required  # Ensure only logged-in users can access
def get_completed_challenges(username):
    # Fetch the user's sesame seeds count
    user_sesame_seeds = current_user.sesame_seeds
    # If the user has between 500 and 999 sesame seeds, complete the challenge "The Sesame Seed Collector"
    if 500 <= user_sesame_seeds <= 999:
        complete_challenge(current_user, "The Sesame Seed Collector")
    # If the user has 1000 or more sesame seeds, complete the challenge "The Sesame Seed Saver"
    if user_sesame_seeds >= 1000:
        complete_challenge(current_user, "The Sesame Seed Saver")
    # If the user has generated 5 or more pages, complete the challenge "The Page Prodigy"
    if current_user.generated_pages_count >= 5:
        complete_challenge(current_user, "The Page Prodigy")
    # If the user has commented on 5 or more pages, complete the challenge "The Feedback Philanthropist"
    for page in current_user.pages:
        if  page.comments.count() >= 5:
            complete_challenge(current_user, "The Feedback Philanthropist")
            break
    # If the user has liked 10 or more pages, complete the challenge "The Social Butterfly"
    user_liked_pages = PageLike.query.filter_by(user_id=current_user.id).count()
    if user_liked_pages >= 10:
        complete_challenge(current_user, "The Social Butterfly")
    # If the user has liked 3 or more pages, complete the challenge "The Like Leader"
    for page in current_user.pages:
        if  page.likes.count() >= 3:
            complete_challenge(current_user, "The Like Leader")
            break
    # Fetch the user by username
    user = User.query.filter_by(username=username).first_or_404()
    # Fetch all completed challenges of the user
    completed_challenges = CompletedChallenge.query.filter_by(user_id=user.id).all()
    # Get the titles of completed challenges
    completed_challenge_titles = [challenge.challenge_title for challenge in completed_challenges]

    # Identifying uncompleted challenges
    all_challenges = {ch["title"]: ch for ch in challenges}
    uncompleted_challenges = [
        {
            "title": title,
            "description": all_challenges[title]["description"],
            "completion_date": None,
            "reward": all_challenges[title].get("reward", None),  # Include reward information
        }
        for title in all_challenges if title not in completed_challenge_titles
    ]
    # Create a list of completed challenges in JSON format
    challenges_json = [
        {
            'user' : username,
            'title': challenge.challenge_title,
            'description': challenge.challenge_description,
            'completion_date': challenge.completion_date.strftime('%Y-%m-%d %H:%M:%S') if challenge.completion_date else None,
            'reward': all_challenges[challenge.challenge_title].get("reward", None),  # Safely get the reward if exists
            'completed': True
        } for challenge in completed_challenges
    ] + [
        {
            'user' : username,
            'title': challenge['title'],
            'description': challenge['description'],
            'completion_date': challenge['completion_date'],
            'reward': challenge.get("reward", None),  # Include reward information for uncompleted as well for consistency
            'completed': False
        } for challenge in uncompleted_challenges
    ]
    # Return the list of completed challenges in JSON format
    return jsonify(challenges_json)

@app.route('/api/pages')
@login_required
def api_pages():
    try:
        # Fetch the query parameter from the request
        query = request.args.get('query', None)
        # If a query is provided, filter the pages by the query
        if query:
            like_query = f'%{query}%'
            pages_query = GeneratedPage.query.filter(
                GeneratedPage.is_unlisted == False,
                db.or_(
                    GeneratedPage.user_input.ilike(like_query),
                    GeneratedPage.theme.ilike(like_query),
                    GeneratedPage.summary.ilike(like_query),
                    User.username.ilike(like_query)
                )
            )
        # If no query is provided, fetch all unlisted pages
        else:
            pages_query = GeneratedPage.query.filter_by(is_unlisted=False)

        # Fetch pages
        pages_data = [
            {
                'uuid': page.uuid,
                'mode': page.mode.replace("_", " "),
                'theme': page.theme,
                'user_input': page.user_input,
                'html_content': page.html_content,
                'username': page.user.username,
                'profile_picture': page.user.profile_picture_url,
                'created_at': page.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'summary': page.summary
            } for page in pages_query.all()
        ]

        # Fetch comments and likes in real-time
        for page_data in pages_data:
            page = GeneratedPage.query.filter_by(uuid=page_data['uuid']).first()
            page_data['likes'] = page.likes.count()
            page_data['comments'] = [
                {
                    'profile_image': comment.user.profile_picture_url,
                    'text': comment.comment_text,
                    'user_id': comment.user_id,
                    'username': comment.user.username,
                    'created_at': comment.created_at.isoformat()  # ISO 8601 format
                } for comment in page.comments
            ]

        # Return the pages data in JSON format
        return jsonify(pages_data)
    except Exception as e:
        app.logger.error(f"Error loading pages: {str(e)}")
        return jsonify(error="Failed to load pages"), 500

@app.route('/purchase/<item_type>/<item_name>', methods=['POST'])
@login_required
def purchase_item(item_type, item_name):
    current_user_seeds = current_user.sesame_seeds
    try:
        # Check if the item has already been purchased
        if Purchase.query.filter_by(user_id=current_user.id, item_type=item_type, item_name=item_name).first():
            return jsonify(success=False, message="Item already purchased.")
        # Get the item cost
        cost = items_for_purchase[item_type][item_name].get('cost', 0)
        # Check if the user has enough sesame seeds to purchase the item
        if cost > current_user_seeds:
            return jsonify(success=False, message="Not enough sesame seeds to purchase.")
        # Deduct the cost from the user's sesame seeds
        current_user.sesame_seeds -= cost
        # If the item is a storage item, add the extra pages to the user's storage
        if item_type == 'storage':
            current_user.extra_storage += items_for_purchase[item_type][item_name].get('extra_pages', 0)
        # Add the purchase to the database
        db.session.add(Purchase(user_id=current_user.id, item_type=item_type, item_name=item_name))
        db.session.commit()
        return jsonify(success=True, message=f"{item_name} purchased successfully.")
    except KeyError:
        abort(404)

@app.route('/dev/gain-seeds')
@login_required
def gain_seeds():
    # Add a condition to restrict access to this route in a production environment
    # For example, check if the app is in debug mode or if the user is authorized as a developer
    if not app.debug:
        return jsonify(success=False, message="This route is not available."), 403

    # Assuming the current_user is the user object thanks to flask_login's @login_required
    current_user.sesame_seeds += 100
    db.session.commit()
    return jsonify(success=True, message="100 sesame seeds added successfully!")

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # Parse JSON data from the request
        data = request.get_json()
        logging.info(data)
        username = data.get('username')
        password = data.get('password')
        # Query the database for the user
        user = User.query.filter(func.lower(User.username) == func.lower(username)).first()
        logging.info(user.username)
        # Check if the user exists and the password is correct
        if user and user.check_password(password):
            login_user(user)
            return jsonify(success=True, redirectUrl=url_for('index', _external=True))
        else:
            return jsonify(success=False, message="Invalid username or password."), 401

    # If the request method is not POST, render the login page
    return render_template("login.html")

@app.route('/logout')
def logout():
    # Log the user out and redirect to the login page
    logout_user()
    return redirect(url_for('login'))


@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        try:
            data = request.get_json()
            username = data.get('username')
            reset_string = data.get('reset_string')
            new_password = data.get('new_password')

            user = User.query.filter_by(username=username).first()

            if not user or user.reset_string != reset_string:
                return jsonify(success=False, message="Username or reset string not found."), 404

            user.set_password(new_password)
            db.session.commit()
            return jsonify(success=True, message="Password reset successfully.")
        except Exception as e:
            return jsonify(success=False, message=str(e)), 500
    return render_template('reset_password.html')

@app.route('/generate', methods=['POST'])
def generate_and_update():
    # Check if the user has reached the generation limit
    if current_user.concurrent_generations >= 3:
        flash("Generation limit reached please wait for your pages to finish generating or the backend to catch up.", 'warning')
        return redirect(url_for('index'))

    # Increment the concurrent generations count and commit the changes to the database
    current_user.concurrent_generations += 1
    db.session.commit()
    logging.info(current_user.concurrent_generations)

    # Remove expired effects
    remove_expired_effects()
    extra_prompt = ""
    top_p = 0.93
    temperature = 1
    max_tokens = 2700
    images_number = 2
    font_override = "none"
    text_override = "none"
    chance = 10
    # Get the form data
    data = request.get_json()
    print(data)
    # Check if the user has reached the generation limit
    if current_user.concurrent_generations >= 3:
        # Flash a warning message
        flash("Generation limit reached please wait for your pages to finish generating or the backend to catch up.",'warning')
        # Redirect to the index page
        return redirect(url_for('index'))

    # Remove expired effects
    remove_expired_effects()


    # Track page generation count
    track_page_generation_count(True)

# Get ingredients from the inventory
    ingredients = InventoryItem.query.filter_by(user_id=current_user.id, type='ingredient').all()

    # Check for specific ingredients
    for ingredient in ingredients:
        if ingredient.name == "A pinch of salt":
            images_number = 4
        elif ingredient.name == "The goblet of wok":
            max_tokens = 3100
            db.session.commit()
        if ingredient.name.lower() == "nitro burger":
            spin_time = 1

    # Get owned modes
    owned_modes = [p.item_name for p in current_user.purchases if p.item_type == 'modes']

    print(data)
    safe = data["safe"]
    try:
        mode  = data["mode"]
    except:
        mode = "regular_mode"
    user_input = data['user_input']

    for effect in active_effect():
        if effect['effect_name'] == 'Blessed Luck':
            chance = 15
        elif effect['effect_name'] == 'Boomer Text':
            text_override = "boomer"
        elif effect['effect_name'] == 'Font Override':
            font_override = "comic"
        elif effect['effect_name'] == 'Javascript Boost':
            extra_prompt = "you will focus on adding a large amount of javascript to make the page fun, interactive, and engaging "
        elif effect['effect_name'] == 'Creative Boost':
            top_p = 0.50
            temperature = 0.50
    print(safe)
    # Award a random item with a 10% chance
    if random.randint(0,20) < chance:
        award_random_item(current_user.id,user_input)
    else:
        logging.info("NO ITEM!!!!")

    # Get theme and visibility from the request data
    theme = data['theme']
    visibility = data['visibility']
    boob = "inactive"

    # Check for active effects
    if "Breast Befriender" in [effect['effect_name'] for effect in active_effect()]:
        boob = "active"

    # Extract the necessary data from the form
    text_override = text_override
    font_override = font_override
    user_input = user_input
    max_tokens = max_tokens
    top_p = top_p
    temperature = temperature
    extra_prompt = extra_prompt
    images_number = images_number
    boob = boob
    description = theme
    visibility = visibility
    mode = mode
    safe = safe

    # Check if the user input length is within a specific range and complete a challenge accordingly
    if 249 <= len(user_input) <= 251 or 349 <= len(user_input) <= 351:
        complete_challenge(current_user, "The Word Smith")

    # Check if the visibility is unlisted and complete a challenge accordingly
    if visibility == 'unlisted':
        complete_challenge(current_user, "The Unlisted Uniter")


    if theme != "silly":
        complete_challenge(current_user, "The Thematic Thinker")

    # Increment the generated pages count and sesame seeds count
    current_user.generated_pages_count += 1
    current_user.sesame_seeds += 10

    # Check if the user has the "Burger of the gods" ingredient and increment the sesame seeds count accordingly
    ingredients = InventoryItem.query.filter_by(user_id=current_user.id, type='ingredient').all()
    for ingredient in ingredients:
        if ingredient.name == "Burger of the gods":
            current_user.sesame_seeds += 20

    # Commit the changes to the database
    db.session.commit()

    # Complete a challenge for generating a page
    complete_challenge(current_user, "The Page Professional")

    # Get the current Flask app object
    app = current_app._get_current_object()

    # Use a ThreadPoolExecutor to generate the HTML content
    with ThreadPoolExecutor() as executor:
        future = executor.submit(generate_html, user_input, theme, safe, current_user.get_id(), mode,max_tokens,images_number,top_p,temperature,extra_prompt,text_override,font_override,boob,app)
        generated_html_content = future.result()

    # Check if the generated HTML content contains specific patterns and complete challenges accordingly
    if generated_html_content:
        if "text-white" in generated_html_content and "bg-white" in generated_html_content:
            complete_challenge(current_user, "The Unreadable")
        elif "background: white" in generated_html_content and "color: white" in generated_html_content:
            complete_challenge(current_user, "The Unreadable")

        if "<script>" in generated_html_content.lower():
            complete_challenge(current_user, "The Code Quest")

        # Check the word count and complete a challenge accordingly
        text = BeautifulSoup(generated_html_content, 'html.parser').get_text()
        word_count = len(text.split())
        if word_count >= 250:
            complete_challenge(current_user, "The Art of Articulation")

    # Decrement the concurrent generations count and commit the changes to the database
    complete_challenge(current_user, "The Page Professional")
    current_user.concurrent_generations -= 1
    db.session.commit()

    # Render the result page with the generated HTML content and other necessary data
    return jsonify({
            'generated_html': generated_html_content,
            'user_input': user_input,
            'theme': theme,
            'visibility': visibility,
            'safe': safe,
            'mode': mode,
        })



@app.route('/', methods=['GET', 'POST'])
@login_required
def index():
    extra_prompt = ""
    top_p = 0.93
    temperature = 1
    spin_time = 5
    max_tokens = 2700
    images_number = 2
    font_override = "none"
    text_override = "none"
    chance = 10
    if current_user.generated_pages_count >= 69:
        # Complete the "Nice..." challenge
        complete_challenge(current_user, "Nice...")
        # Award the special item "The sigma amulet"
        award_special_item(current_user, "The sigma amulet")

    # Check if the request method is POST
    if request.method == 'POST':
        # Check if the user has reached the generation limit
        if current_user.concurrent_generations >= 3:
            # Flash a warning message
            flash("Generation limit reached please wait for your pages to finish generating or the backend to catch up.",'warning')
            # Redirect to the index page
            return redirect(url_for('index'))

        # Remove expired effects
        remove_expired_effects()


        # Track page generation count
        track_page_generation_count(True)

        # Get ingredients from the inventory
        ingredients = InventoryItem.query.filter_by(user_id=current_user.id, type='ingredient').all()

        # Check for specific ingredients
        for ingredient in ingredients:
            if ingredient.name == "A pinch of salt":
                images_number = 4
            elif ingredient.name == "The goblet of wok":
                max_tokens = 3100
                db.session.commit()
            if ingredient.name.lower() == "nitro burger":
                spin_time = 1

        # Get owned modes
        owned_modes = [p.item_name for p in current_user.purchases if p.item_type == 'modes']

        data = request.get_json()
        print(data)
        safe = data["safe"]
        try:
            mode  = data["mode"]
        except:
            mode = "regular_mode"
        user_input = data['user_input']

        for effect in active_effect():
            if effect['effect_name'] == 'Blessed Luck':
                chance = 15
            elif effect['effect_name'] == 'Boomer Text':
                text_override = "boomer"
            elif effect['effect_name'] == 'Font Override':
                font_override = "comic"
            elif effect['effect_name'] == 'Javascript Boost':
                extra_prompt = "you will focus on adding a large amount of javascript to make the page fun, interactive, and engaging "
            elif effect['effect_name'] == 'Creative Boost':
                top_p = 0.50
                temperature = 0.50

        # Award a random item with a 10% chance
        if random.randint(0,20) < chance:
            award_random_item(current_user.id,user_input)
        else:
            logging.info("NO ITEM!!!!")

        # Get theme and visibility from the request data
        theme = data['theme']
        visibility = data['visibility']
        boob = "inactive"

        # Check for active effects
        if "Breast Befriender" in [effect['effect_name'] for effect in active_effect()]:
            boob = "active"

        # Render the loading page
        return render_template(
            'loading.html',
            user_input=user_input,
            theme=theme,
            visibility=visibility,
            safe=safe,
            mode=mode,
            images_number=images_number,
            max_tokens=max_tokens,
            top_p=top_p,
            temperature=temperature,
            extra_prompt=extra_prompt,
            spin_time=spin_time,
            text_override=text_override,
            font_override=font_override,
            boob=boob,
        )

    # If the request method is GET, render the index page
    logging.info("GET request received, rendering index page")
    owned_themes = set(p.item_name for p in current_user.purchases if p.item_type == 'themes')
    owned_themes.add('silly')
    owned_modes = set(p.item_name for p in current_user.purchases if p.item_type == 'modes')
    owned_modes.add('regular_mode')
    owned_modesreturn = list(owned_modes)

    # Construct the list of themes wi/dev/gain-seedsth their descriptions to pass to the template.
    themes_for_template = [{'name': theme, 'description': items_for_purchase['themes'][theme]['description']} for theme in owned_themes]

    # Check if the user has already purchased an increase in prompt length, otherwise default to 250.
    prompt_length = next((items_for_purchase['Prompt Length Increase']['prompt_length']['length'] for p in current_user.purchases if p.item_type == 'Prompt Length Increase'), 250)

    # Check for active effects
    for effect in active_effect():
        if effect['effect_name'] == 'Extra Characters':
            prompt_length = prompt_length + 100

    # Track page generation count
    page_generation_count = track_page_generation_count(False)

    # Try to get the total files count, default to 0 if an error occurs
    try:
        total_files = db.session.query(GeneratedPage).count()
    except:
        total_files = 0

    # Get alerts for the current user
    alerts = Alert.query.filter_by(user_id=current_user.id).all()
    alerts_data = [{
        'id': alert.id,
        'alert_type': alert.alert_type,
        'date': alert.date.strftime('%Y-%m-%d %H:%M:%S'),
        'message': alert.message
    } for alert in alerts]
    number_of_alerts = len(alerts_data)

    # Get total sesame seeds in circulation
    total_sesame_seeds_in_circulation = db.session.query(func.sum(User.sesame_seeds)).scalar()

    # Get total items in circulation
    total_items_in_circulation = InventoryItem.query.count()

    # Get total challenges completed
    total_challenges_completed = CompletedChallenge.query.filter(CompletedChallenge.completion_date.isnot(None)).count()

    # Get total users
    total_users = User.query.count()

    # Render the index page
    return render_template(
        'index.html',
        total_challenges=total_challenges_completed,
        total_users=total_users,
        total_sesame_seeds=total_sesame_seeds_in_circulation,
        total_items=total_items_in_circulation,
        theme_groups=themes_for_template,  # Pass the correct variable here
        total_files=total_files,
        page_generation_count=page_generation_count,
        current_username=current_user.username,
        prompt_length=prompt_length,
        sesame_seeds=current_user.sesame_seeds,
        owned_modes=owned_modesreturn,
        spin_time=spin_time,
        alerts_data=alerts_data,
        number_of_alerts=number_of_alerts,
    )

@app.route('/encrypt', methods=['POST'])
def encrypt_text():
    from cryptography.fernet import Fernet
    # This key should be securely stored and managed, but is hardcoded here for demonstration
    key = b'm99uo6ItvZ9eE2zHgcCtdFn02Bkoawd-TgQ9R09VPxs='  # Replace 'your-secret-key-here' with your actual key
    cipher_suite = Fernet(key)

    data = request.get_json()
    if 'text' not in data:
        return jsonify({'error': 'No text provided'}), 400

    text = data['text']
    encrypted_text = cipher_suite.encrypt(text.encode('utf-8'))

    return jsonify({'encrypted_text': encrypted_text.decode('utf-8')}), 200


@app.route('/result', methods=['GET'])
def results():
    encrypted_params = request.args.get('params', None)
    uuid = request.args.get('uuid', None)




    # Check if UUID is provided and valid
    if uuid:
        redirect_entry = RequestRedirect.query.filter_by(uuid=uuid).first()
        if redirect_entry and datetime.utcnow() < redirect_entry.created_at + timedelta(minutes=10):
            return redirect(redirect_entry.redirect_url)
        else:
            try:
                db.session.delete(redirect_entry)
                db.session.commit()
            except:
                logging.info("INVALID UUID DELETION ATTEMPTED")
            return jsonify({'error': 'Invalid or expired UUID'}), 404
    elif encrypted_params and encrypted_params != None:
        decrypted_params = decrypt_text(encrypted_params)
        params = json.loads(decrypted_params)
        print(params)
        generated_html = params['generated_html']
        user_input = params['user_input']
        theme = params['theme']
        visibility = params['visibility']
        safe = params['safe']
        mode = params['mode']
    else:
        return jsonify({'error': 'Missing parameters'}), 400
    ingredients = InventoryItem.query.filter_by(user_id=current_user.id, type='ingredient').all()

    # Check for specific ingredients
    spin_time = 5
    for ingredient in ingredients:
        if ingredient.name.lower() == "nitro burger":
            spin_time = 1

    # Check if the current URL already has a UUID and use it instead of generating a new one
    existing_redirect = RequestRedirect.query.filter_by(redirect_url=request.url).first()
    if existing_redirect:
        new_uuid = existing_redirect.uuid
    else:
        # Generate a new UUID for this request and store the redirect URL
        new_uuid = str(uuid4())
        new_redirect = RequestRedirect(uuid=new_uuid, redirect_url=request.url)
        db.session.add(new_redirect)
        db.session.commit()

    # Render the results page with the URL parameters
    return render_template(
        'result.html',
        generated_html=generated_html,
        user_input=user_input,
        theme=theme,
        visibility=visibility,
        safe=safe,
        mode=mode,
        spin_time=spin_time,
        uuid=new_uuid  # Pass the UUID to the template
    )

@app.route('/user/<username>')
@login_required
def api_profile(username):
    # Convert user ID to username if a numeric value is passed
    try:
        user = User.query.get(int(username))
        logging.info(user)
        if not user:
            abort(404)
        username = user.username
    except:
        user = User.query.filter_by(username=username).first_or_404()

    isCurrentUser = username == current_user.username

    # Fetch the generated pages for the user
    pages = GeneratedPage.query.filter_by(user_id=user.id, is_unlisted=False).all() if not isCurrentUser else GeneratedPage.query.filter_by(user_id=user.id).all()
    # Fetch the completed challenges count for the user
    user_completed_challenges = CompletedChallenge.query.filter_by(user_id=user.id).count()

    # Calculate the total storage quota and current storage used
    total_storage_quota = 10 + user.extra_storage
    current_storage_used = len(pages)

    # Prepare the response data
    response_data = {
        'id': user.id if isCurrentUser else None,
        'username': user.username,
        'generated_pages_count': user.generated_pages_count,
        'sesame_seeds': user.sesame_seeds if isCurrentUser else None,
        'current_storage_used': current_storage_used,
        'total_storage_quota': total_storage_quota,
        'total_challenges': len(challenges),
        'completed_challenges_count': user_completed_challenges,
        'bio': user.bio or f"Hi, I'm {user.username}",
        'profile_picture_url': user.profile_picture_url,
        'proudest_achievement': user.proudest_achievement or "No Achievement chosen",
        'saved_pages': [
            {
                'id': page.id,
                'uuid': page.uuid,
                'theme': page.theme,
                'user_input': page.user_input,
                'created_at': page.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'summary': page.summary,
                'is_unlisted': page.is_unlisted
            } for page in pages
        ],
        'likes_sent': user.page_likes.count(),
        'comments_sent': user.page_comments.count()
    }

    # Return the response data as JSON
    return jsonify(response_data)


@app.route('/profile/customize', methods=['POST'])
@login_required
def customize_profile():
    # Direct reference to the logged-in user
    user = current_user
    # Get the bio, proudest achievement, and image search prompt from the request
    bio = request.form.get('bio', None)
    proudest_achievement = request.form.get('proudest_achievement', None)
    prompt = request.form.get('image_search_prompt')

    # Sanitize the bio if it exists and is less than 150 characters
    if bio is not None and len(bio) < 150:
        sanitized_bio = bleach.clean(bio, strip=True)
        user.bio = sanitized_bio

    # If a prompt exists, query an image with it
    if prompt:
        image_url = query_image_with_prompt(prompt)
        # If an image is found, set it as the user's profile picture
        if image_url:
            user.profile_picture_url = image_url
        else:
            flash('No image found for the provided prompt.', 'warning')
    else:
        pass

    # If a proudest achievement exists and it is a completed challenge, set it as the user's proudest achievement
    if proudest_achievement and any(
        challenge.challenge_title == proudest_achievement for challenge in user.completed_challenges):
        user.proudest_achievement = proudest_achievement
    db.session.commit()

    # Flash a success message and redirect to the user's profile
    flash('Your profile has been updated.', 'success')
    return redirect(url_for('profile', username=user.username))

@app.route('/use-item/<int:item_id>', methods=['POST'])
@login_required
def use_item(item_id):
    # Get the item from the inventory
    item = InventoryItem.query.get_or_404(item_id)
    # Check if the item belongs to the current user
    if item.user_id != current_user.id:
        return jsonify(success=False, message='This item does not belong to you.'), 403
    # Check if the item is consumable
    if item.type != 'consumable':
        return jsonify(success=False, message='This item is not consumable and cannot be used in this way.'), 400

    # Get the current time
    current_time = datetime.utcnow()
    # Check if the item has an effect
    if item.name in effect_properties:
        # Get the effect information
        effect_info = effect_properties[item.name]
        effect_name = effect_info["name"]
        effect_duration_hours = effect_info["duration"]
        # Calculate the effect duration
        effect_duration_hours = (1 + (item.quality / 100) * 0.75) + effect_duration_hours

        # Check if the user has "The everything elixer"
        if "The everything elixer" in [ingredient.name for ingredient in InventoryItem.query.filter_by(user_id=current_user.id).all()]:
            # Increase the effect duration by 15%
            effect_duration_hours *= 1.15

        # Check if the user already has the effect active
        existing_effect = Effect.query.filter_by(user_id=current_user.id, effect_name=effect_name).filter(Effect.expires_at > current_time).first()

        # If the user already has this effect active, prevent them from using the item again
        if existing_effect:
            return jsonify(success=False, message=f'You already have an active "{effect_name}" effect. Please wait until it expires to use this item again.'), 400

        # If the effect is not currently active for the user, apply the effect and remove the item from inventory
        expires_at = current_time + timedelta(hours=effect_duration_hours)
        new_effect = Effect(
            user_id=current_user.id,
            effect_name=effect_name,
            expires_at=expires_at
        )
    active_effects_count = len(active_effect())

    # Check if the item is "The busty bun toaster"
    if item.name == "The busty bun toaster":
        # Add the new effect to the database
        db.session.add(new_effect)
        db.session.commit()
        active_effects_count = len(active_effect())
        # Check if the user has more than 3 active effects
        if active_effects_count >= 3:
            complete_challenge(current_user, "The Effect Enthusiast")
            award_special_item(current_user, "The everything elixer")
        return jsonify(success=True, message=f'{item.name} has been successfully used. "{effect_name}" effect will last for {effect_duration_hours} hours.')

    else:
        # Add the new effect to the database
        db.session.add(new_effect)
        # Remove the item from the user's inventory
        db.session.delete(item)
        db.session.commit()
        active_effects_count = len(active_effect())
        # Check if the user has more than 3 active effects
        if active_effects_count >= 3:
            complete_challenge(current_user, "The Effect Enthusiast")
            award_special_item(current_user, "The everything elixer")
        return jsonify(success=True, message=f'{item.name} has been successfully used. "{effect_name}" effect will last for {effect_duration_hours} hours.')

@app.route('/profile/', defaults={'username': None})
@app.route('/profile/<username>')
@login_required
def profile(username):
    # Default to current user's username if none is provided
    if username is None:
        username = current_user.username

    # Query for the user based on the username
    user = User.query.filter_by(username=username).first_or_404()

    # Query for the current user's completed challenges
    completed_challenges = CompletedChallenge.query.filter_by(user_id=user.id).all()
    completed_challenge_titles = [challenge.challenge_title for challenge in completed_challenges]

    # Check if the profile being viewed is the current user's own profile
    is_current_user = (user.username == current_user.username)

    # Render the profile template with appropriate data
    return render_template('profile.html',
                           user=user,
                           current_username=current_user.username,
                           completed_challenges=completed_challenge_titles,
                           is_current_user=is_current_user)

@app.route('/delete-page/<uuid>', methods=['DELETE'])
@login_required
def delete_page(uuid):
    # Fetch the page with the provided UUID
    page = GeneratedPage.query.filter_by(uuid=uuid).first_or_404()
    # Check if the current user is the owner of the page
    if page.user_id != current_user.id:
        abort(403)  # Forbidden access if the user doesn't own the page
    # Delete likes associated with the page
    PageLike.query.filter_by(page_id=page.id).delete()
    # Delete comments associated with the page
    PageComment.query.filter_by(page_id=page.id).delete()
    # Delete the page
    db.session.delete(page)
    db.session.commit()
    # Complete the challenge for the user
    complete_challenge(current_user,"The Page Punisher")
    # Return a success message
    return jsonify({'message': 'Page deleted successfully.'})


@app.route('/save-page', methods=['POST'])
@login_required
def save_page():
    # Fetch the data from the request
    data = request.json
    # Check if the user has reached the storage limit
    print("HTML CONTENT NOW",data.get('html_content'))
    if current_user.pages.count() >= 10 + current_user.extra_storage:
        return jsonify(status='failure', message='Storage limit reached. Please purchase more storage to save new pages.')

    # Generate a UUID for the new page
    page_uuid = str(uuid4())
    existing_pages = GeneratedPage.query.filter_by(html_content=data.get('html_content')).all()
    if existing_pages:
        return jsonify(status='failure', message='This content already exists. Please create unique content.')
    is_unlisted = data.get('visibility') == 'unlisted'
    # Generate a summary for the page
    summary = generate_summary(data['html_content'])
    # Create a new page object
    new_page = GeneratedPage(
        uuid=page_uuid,
        theme=data.get('theme'),
        user_input=data.get('user_input'),
        html_content=data.get('html_content'),
        summary=summary,
        user_id=current_user.id,
        is_unlisted=is_unlisted,
        mode=data.get("mode")
    )
    # Count the number of unlisted pages for the user
    user_unlisted_pages_count = len([page for page in current_user.pages if page.is_unlisted])
    # Check if the user has completed the Incognito challenge
    if user_unlisted_pages_count >= 10:
        complete_challenge(current_user, "The Incognito")
        award_special_item(current_user, "The busty bun toaster")
    # Check if the user has completed the Prolific Publisher challenge
    if  current_user.pages.count() >= 10:
        complete_challenge(current_user, "The Prolific Publisher")

    # Set the chance of getting a random item
    chance = 5
    # Check if the user has the Blessed Luck effect
    for effect in active_effect():
            if effect['effect_name'] == 'Blessed Luck':
                chance = 8
    # Roll the dice to see if the user gets a random item
    if random.randint(0,10) < chance:
        award_random_item(current_user.id,data['user_input'])
    else:
        logging.info("NO ITEM!!!!")
    # Add sesame seeds to the user's account
    current_user.sesame_seeds += 15
    # Check if the user has the Burger of the gods
    if InventoryItem.query.filter_by(user_id=current_user.id, type='ingredient', name="Burger of the gods").first():
        current_user.sesame_seeds += 30

    # Add the new page to the database
    db.session.add(new_page)
    db.session.commit()

    # Return a success message
    return jsonify(status='success', message='Page saved successfully.')


@app.route('/browse')
@login_required
def browse():
    return render_template('browse.html')

@app.route('/view/<uuid>')
def view_page(uuid):
    page = GeneratedPage.query.filter_by(uuid=uuid).first_or_404()
    return render_template('view.html', page=page)

@app.route('/usepolicy')
def view_policy():
    try:
        complete_challenge(current_user, "The Responsible Reader")
    except:
        pass
    return render_template('usepolicy.html')

@app.route('/download/<uuid>')
def download(uuid):
    page = GeneratedPage.query.filter_by(uuid=uuid).first_or_404()
    content = page.html_content.encode('utf-8')
    return Response(content,
                    mimetype="application/html",
                    headers={"Content-Disposition":
                             f"attachment; filename={page.uuid}.html"})


@app.route('/generate_name', methods=['POST'])
def generate_name():
    modifiers = ["outrageous", "hilarious", "light-hearted", "creative", "out of the box", "inspired", "nostalgic", "imaginative", "quirky", "whimsical", "unique", "innovative", "eccentric", "unconventional", "retro", "vintage", "adventurous", "playful", "witty", "sophisticated", "elegant", "mystical", "enigmatic", "fanciful", "fantastical", "dreamy", "serene", "ethereal", "otherworldly", "surreal", "bizarre", "absurd", "satirical", "ironic", "droll", "cryptic", "esoteric", "idiosyncratic", "offbeat", "peculiar", "captivating", "enchanting", "exotic", "explorative", "provocative", "thought-provoking", "stimulating", "intriguing", "expressive", "imaginative", "inventive", "original", "unorthodox", "whacky"]
    inputs = load_inputs()
    response = openai.Completion.create(
        engine=inputs['engines']['secondary_engine'],
        prompt=inputs['prompts']['website_name_prompt'].format(modifier=random.choice(modifiers)),
        max_tokens=inputs['tokens']['website_name_token_size'],
        temperature=inputs['parameters']['temperature'],
        top_p=inputs['parameters']['top_p'] # add this line
    )
    return jsonify({"name": response.choices[0].text.strip().strip('"')})

@app.route('/leaderboard')
def leaderboard():
    return render_template('leaderboard.html')

@app.route('/leaderboard/api')
def leaderboard_api():
    # Get the username from the request and convert it to lowercase
    search_username = request.args.get("username", "").strip().lower()

    # Subquery for counting likes received from others on the user's generated pages
    subquery_likes = db.session.query(
        GeneratedPage.user_id,
        func.count(PageLike.id).label('likes_count')
    ).join(PageLike, GeneratedPage.id == PageLike.page_id
    ).filter(GeneratedPage.user_id != PageLike.user_id
    ).group_by(GeneratedPage.user_id).subquery()

    # Subquery for counting comments received from others on the user's generated pages
    subquery_comments = db.session.query(
        GeneratedPage.user_id,
        func.count(PageComment.id).label('comments_count')
    ).join(PageComment, GeneratedPage.id == PageComment.page_id
    ).filter(GeneratedPage.user_id != PageComment.user_id
    ).group_by(GeneratedPage.user_id).subquery()

    # Subquery for counting generated (saved) pages per user
    subquery_saved_pages = db.session.query(
        GeneratedPage.user_id,
        func.count('*').label('saved_pages_count')
    ).group_by(GeneratedPage.user_id).subquery()

    # Main query adjusted to include saved pages count and exclude self-likes and self-comments
    rank_query = db.session.query(
        User.profile_picture_url,
        User.username,
        User.generated_pages_count,
        func.coalesce(subquery_likes.c.likes_count, 0).label('likes_received'),
        func.coalesce(subquery_comments.c.comments_count, 0).label('comments_received'),
        func.coalesce(subquery_saved_pages.c.saved_pages_count, 0).label('saved_pages'),
        User.sesame_seeds,
        func.rank().over(order_by=[User.generated_pages_count.desc(),
                                    func.coalesce(subquery_likes.c.likes_count, 0).desc(),
                                    func.coalesce(subquery_comments.c.comments_count, 0).desc(),
                                    User.sesame_seeds.desc()]).label('rank')
    ).outerjoin(
        subquery_likes, User.id == subquery_likes.c.user_id
    ).outerjoin(
        subquery_comments, User.id == subquery_comments.c.user_id
    ).outerjoin(
        subquery_saved_pages, User.id == subquery_saved_pages.c.user_id
    ).subquery()

    # If a username is provided, filter the final query by the username
    if search_username:
        final_query = db.session.query(rank_query).filter(func.lower(rank_query.c.username).like(f"%{search_username}%"))
        total_results = final_query.count()
    else:
        final_query = db.session.query(rank_query)
        total_results = final_query.count()

    # Limit the results to 10 and convert them to a list of dictionaries
    users = final_query.limit(15).all()
    leaderboard = [{
        "rank": user.rank,
        "username": user.username,
        "profile_picture_url": user.profile_picture_url,
        "generated_pages": user.generated_pages_count,
        "saved_pages": user.saved_pages,
        "likes_received": user.likes_received,
        "comments_received": user.comments_received,
        "sesame_seeds": user.sesame_seeds,
        "total_results": total_results  # Optional, gives an idea of total users in the query
    } for user in users]

    # Return the leaderboard as a JSON response
    return jsonify(leaderboard)

if __name__ == '__main__':
    with app.app_context():
        User.query.update({User.concurrent_generations: 0})
        db.session.commit()
        db.create_all()
    context = ('certificate.crt', 'private.key')
    app.run(host='0.0.0.0',port=443, ssl_context=context,threaded=True)
