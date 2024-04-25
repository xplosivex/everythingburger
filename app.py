import os, logging, openai, yaml, json, random
import markdown
from passlib.ifc import PasswordHash
from bs4 import BeautifulSoup
import requests
import json
from flask_migrate import Migrate
from flask import abort, flash, Flask, Response, render_template, request, stream_with_context, send_from_directory, jsonify, redirect, url_for, session, current_app
from datetime import datetime
from sqlalchemy.sql import func
from flask_sqlalchemy import SQLAlchemy
from uuid import uuid4
from datetime import datetime
import secrets
import string
import time
import bleach
from passlib.hash import pbkdf2_sha256
from flask_login import UserMixin, LoginManager, login_user, logout_user, current_user, login_required
from threading import Thread
from flask_sse import sse
from concurrent.futures import ThreadPoolExecutor
import functools


MAINTENANCE_MODE = False



logging.basicConfig(filename='console.log', filemode='a', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logging.getLogger().addHandler(logging.StreamHandler())

app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['TEMPLATES_AUTO_RELOAD'] = True
openai.api_key = ""
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///pages.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
app.secret_key = '' 

challenges = [
    {"title": "The Whimsical Word Wizard", "description": "Generate a page containing the word 'wizard'."},
    {"title": "The Fecal Fanatic", "description": "Generate a prompt containing the word 'poop'."},
    {"title": "The Sesame Seed Collector", "description": "Accumulate a total of 500 sesame seeds."},
    {"title": "The Comment Crusader", "description": "Leave comments on 5 different posts."},
    {"title": "The Image Seeker", "description": "Create a page that contains at least one image."},
    {"title": "The Thematic Thinker", "description": "Generate pages a theme other than the default of silly."},
    {"title": "The Word Smith", "description": "Generate prompt that contains the maximum amount of characters."},
    {"title": "The Social Butterfly", "description": "Like 10 pages."},
    {"title": "The Prolific Publisher", "description": "Save a total of 10 pages."},
    {"title": "The Store Spree", "description": "Purchase five items from the store."},
    {"title": "The Art of Articulation", "description": "Generate a page containing over 250 words."},
    {"title": "The Feedback Philanthropist", "description": "Receive 5 comments on a single page you've created."},
    {"title": "The Eclectic Collector", "description": "Own at least one item from each category in the store."},
    {"title": "The Sesame Seed Saver", "description": "Have 1000 sesame seeds at any one time."},
    {"title": "The Creative Commentator", "description": "Write a comment containing more than 50 words."},
    {"title": "The Page Punisher", "description": "Delete a page."},
    {"title": "The Unlisted Uniter", "description": "Create an unlisted page."},
    {"title": "The Responsible Reader", "description": "Read the full user policy."},
    {"title": "The Code Quest", "description": "Generate a page that includes javascript."},
    {"title": "The Unreadable", "description": "Generate a page that includes white text on a white background."},
    {"title": "The Like Leader", "description": "Have one of your pages receive 3 likes."},
    {"title": "The Page Professional", "description": "Generate your first page."},
    {"title": "The Page Prodigy", "description": "Generate 5 pages."},
]

items_for_purchase = {
"themes": {
    "silly": {"description": "Embrace a whimsical design with playful elements and vibrant colors. Let the writing reflect a humorous and entertaining tone.", "cost": 0},
    "professional": {"description": "Opt for a clean, neutral-colored design exuding formality and professionalism. Maintain a business-like tone in the writing.", "cost": 15},
    "chaotic": {"description": "Engage the user with unpredictable layouts and elements. A spastic and chaotic writing style should prevail.", "cost": 35},
    "formal": {"description": "Stick to a structured layout, using muted colors. The writing should be formal and respectful.", "cost": 40},
    "artistic": {"description": "Showcase creative visuals and unique design patterns, accompanying them with a creative and artistic writing style.", "cost": 25},
    "nature": {"description": "Immerse in nature-inspired designs, earthy colors, and scenic backgrounds. The writing should flow naturally, inspired by the outdoors.", "cost": 20},
    "techie": {"description": "Display digital elements, interactive features, and modern design trends, paired with a techie, futuristic writing style.", "cost": 40},
    "historical": {"description": "Reflect history through vintage fonts, classic layouts, and period-appropriate colors. The writing should echo a historical and old-fashioned tone.", "cost": 10},
    "retro": {"description": "Revisit the early 2000s with nostalgic design elements and colors. The writing should evoke a retro, nostalgic feel.", "cost": 30},
    "futuristic": {"description": "Adopt modern, sleek, and minimalist styles representing a futuristic outlook. The writing should mirror a modern, forward-thinking tone.", "cost": 25},
    "outlandish": {"description": "Dare to be different with unconventional and unexpected design elements, alongside an outrageous, dark-humor based writing style.", "cost": 50},
    "minimalist": {"description": "Embrace simplicity with a limited color palette and minimal design elements. The writing should reflect a minimalist, straightforward tone.", "cost": 20},
    "unbiased": {"description": "Adhere to standard web design practices, paired with a neutral and unbiased writing style, as no specific thematic guidance has been provided.", "cost": 55}},
"Prompt Length Increase": {
    "prompt_length": { "description":"Extend how many character you can use when generating pages","length":350, "cost":100},

},
"storage": {
    "storage_10": {"description": "Add 10 extra pages to your storage.", "extra_pages": 10, "cost": 50},
    "storage_20": {"description": "Add 20 extra pages to your storage.", "extra_pages": 20, "cost": 90},
    "storage_30": {"description": "Add 30 extra pages to your storage.", "extra_pages": 30, "cost": 150}
}, "modes": {
    "regular_mode": {"description":"Good old page generation the way momma used to make it.","cost":0},
    "schizo_mode": {"description": "Generate pages with unpredictable, chaotic twists and turns, as if multiple personalities were creating them.", "cost": 200},
    "third_grader_mode": {"description": "Generate simple, straightforward pages with the grammatical style and personality of a third grader.", "cost": 80},
    "pirate_mode": {"description": "Yarrr! Generate page with the swagger of a pirate. Expect nautical terms, treasure hunts, and swashbuckling adventures.", "cost": 90},
    "shitpost_mode": {"description": "Generate pages as if you were a dorito loving based and red pilled redditor." , "cost": 150}

}}
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))



class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    reset_string = db.Column(db.String(120), nullable=True)
    generated_pages_count = db.Column(db.Integer, default=0)
    sesame_seeds = db.Column(db.Integer, default=0,nullable=False)
    extra_storage = db.Column(db.Integer, default=0, nullable=False)
    bio = db.Column(db.Text, default=lambda: None)  
    profile_picture_url = db.Column(db.String(512), default="https://img.freepik.com/free-vector/hamburger_53876-25481.jpg")  
    proudest_achievement = db.Column(db.Text, default=lambda: None)


    def generate_reset_string(self):
        self.reset_string = secrets.token_hex(16)  
        db.session.commit()
        return self.reset_string

    def set_password(self, password):
        self.password_hash = pbkdf2_sha256.hash(password)

    def check_password(self, password):
        return pbkdf2_sha256.verify(password, self.password_hash)

class GeneratedPage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, nullable=False)
    theme = db.Column(db.String(120), nullable=False)
    user_input = db.Column(db.Text, nullable=False)
    html_content = db.Column(db.Text, nullable=False)
    summary = db.Column(db.Text, nullable=False)
    mode = db.Column(db.String(120), nullable=True, default="regular")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  
    is_unlisted = db.Column(db.Boolean, default=False)
    user = db.relationship('User', backref=db.backref('pages', lazy=True))


class PageLike(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    page_id = db.Column(db.Integer, db.ForeignKey('generated_page.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    page = db.relationship('GeneratedPage', backref=db.backref('likes', lazy=True))
    user = db.relationship('User', backref=db.backref('page_likes', lazy=True))


class PageComment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    page_id = db.Column(db.Integer, db.ForeignKey('generated_page.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    comment_text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    page = db.relationship('GeneratedPage', backref=db.backref('comments', lazy=True))
    user = db.relationship('User', backref=db.backref('page_comments', lazy=True))

class Purchase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    item_type = db.Column(db.String(120), nullable=False)
    item_name = db.Column(db.String(120), nullable=False)
    purchase_date = db.Column(db.DateTime, default=datetime.utcnow)


    user = db.relationship('User', backref=db.backref('purchases', lazy=True))

class CompletedChallenge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    challenge_title = db.Column(db.String(255), nullable=False)
    challenge_description = db.Column(db.Text, nullable=False)  
    completion_date = db.Column(db.DateTime, default=datetime.utcnow)  

    user = db.relationship('User', backref=db.backref('completed_challenges', lazy=True))

class Template(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    template_name = db.Column(db.String(255), nullable=False)
    user_input = db.Column(db.Text, nullable=False)
    theme = db.Column(db.String(80), nullable=False)
    visibility = db.Column(db.String(80), nullable=False)
    safe = db.Column(db.Boolean, default=True)
    mode = db.Column(db.String(80), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    user = db.relationship('User', backref=db.backref('templates', lazy=True))

migrate = Migrate(app, db)

def complete_challenge(user, challenge_title):
    global challenges
    challenge = next((ch for ch in challenges if ch['title'] == challenge_title), None)

    if challenge:
        
        existing_challenge = CompletedChallenge.query.filter_by(
            user_id=user.id, challenge_title=challenge['title']).first()
        if not existing_challenge:
            completed_challenge = CompletedChallenge(
                user_id=user.id,
                challenge_title=challenge['title'],
                challenge_description=challenge['description']
            )
            db.session.add(completed_challenge)
            db.session.commit()
            logging.info(f"Challenge '{challenge_title}' completed by user {user.username}")
            return True  

    return False

def query_valueserpapi(query,safe="active"):
    params = {
    'api_key': '',
      'search_type': 'images',
      'q': f'{query}',
      'num': '5',
      'safe': f'{safe}'
    }

    
    api_result = requests.get('', params)

    
    data = api_result.json()
    try:
        if 'image_results' in data and data['image_results']:
            url_conversion = data["image_results"]

            for attempt in range(2):  
                random_image_info = random.choice(url_conversion)
                image_url = random_image_info["image"]
                response = requests.head(image_url, allow_redirects=True)

                if response.status_code != 404:
                    return image_url  
                else:
            	    return None  
        else:
            return None
    except Exception as e:
        return None
    

def load_inputs():
    with open('inputs.yml', 'r') as file:
        return yaml.safe_load(file)

def generate_html(user_input, theme, safe,user_id, mode, app):
    start_time = datetime.now()
    logging.info(f'Start generating HTML for {user_input}: {start_time}')
    inputs = load_inputs()
    param_type = 'parameters'
    theme_prompt = items_for_purchase['themes'][theme]['description']
    logging.info(f'mode choosen: {mode}')
    if mode == "regular_mode":
        prompt = "html_prompt"
    elif mode == "schizo_mode":
        prompt = "schizo_prompt"
    elif mode == "third_grader_mode":
        prompt = "third_prompt"
    elif mode == "pirate_mode":
        prompt = "pirate_prompt"
    elif mode == "shitpost_mode":
        prompt = "shitposter_prompt"
    else:
        prompt = "html_prompt"
    formatted_prompt = inputs['prompts'][prompt].format(
            user_input=user_input,
            theme_prompt=theme_prompt,
        )
    logging.info(f"P AND TEMP PARAMS: {inputs[param_type]}")
    logging.info(f"Prompt: {formatted_prompt}")
    response = openai.Completion.create(
        engine=inputs['engines']['default_engine'],
        prompt=formatted_prompt,
        max_tokens=inputs['tokens']['html_token_size'],
        temperature=inputs[param_type]['temperature'],
        top_p=inputs[param_type]['top_p']
    )
    with app.app_context():
        user = User.query.get(user_id)
        if 'poop' in response['choices'][0]['text'].lower():
            complete_challenge(user, "The Fecal Fanatic")
        if 'wizard' in response['choices'][0]['text'].lower():
            complete_challenge(user, "The Whimsical Word Wizard")
        updated_html = update_image_urls_in_html(response['choices'][0]['text'].strip().strip('"'),safe, user_id)
        end_time = datetime.now()
        logging.info(f'Finished generating HTML for {user_input}: {end_time}, took: {end_time - start_time}')
        return updated_html

@app.before_request
def check_for_maintenance():
    if MAINTENANCE_MODE:
        return render_template('maintenance.html'), 503

@app.route('/save/templates', methods=['POST'])
@login_required
def store_template():
    current_templates_count = Template.query.filter_by(user_id=current_user.id).count()
    if current_templates_count >= 10:
        return jsonify({"error": "Template limit reached. You can only save up to 10 templates."}), 403
    data = request.json
    user_input = data['user_input']
    user_input = bleach.clean(user_input,strip=True)
    if len(user_input) < 30:
        template_name = ''.join(random.choices(string.ascii_letters + string.digits, k=30))
    else:
        template_name = user_input[:10] + ''.join(random.choices(string.ascii_letters + string.digits, k=10)) + user_input[-10:]

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
    return jsonify({"message": "Template stored successfully", "template_id": new_template.id}), 201

@app.route('/templates/<int:template_id>', methods=['DELETE'])
@login_required
def delete_template(template_id):
    template = Template.query.get_or_404(template_id)
    if template.user_id != current_user.id:
        abort(403)  
    db.session.delete(template)
    db.session.commit()
    return jsonify({"message": "Template deleted successfully"}), 204

@app.route('/load/templates', methods=['GET'])
@login_required
def load_templates():
    templates = Template.query.filter_by(user_id=current_user.id).all()
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
    return jsonify(templates_data)

@app.route('/load/templates/<int:template_id>', methods=['GET'])
@login_required
def load_template_by_id(template_id):
    template = Template.query.filter_by(id=template_id, user_id=current_user.id).first()

    if template is None:
        return jsonify({"error": "Template not found"}), 404

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
@login_required  
def challenge():
    return render_template('challenges.html', current_username=current_user.username)

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter(func.lower(User.username) == func.lower(username)).first()
        if user:
            flash('Username already exists.', 'error')
            return jsonify(success=False, message='Username already exists.')

        new_user = User(username=username)
        new_user.set_password(password)
        reset_string = new_user.generate_reset_string()
        db.session.add(new_user)
        db.session.commit()

        
        return jsonify(success=True, reset_string=reset_string, message='Signup successful. Please save your reset string securely.')

    return render_template('signup.html')

@app.route('/like_page/<uuid>', methods=['POST'])
@login_required
def like_page(uuid):
    page = GeneratedPage.query.filter_by(uuid=uuid).first_or_404()
    existing_like = PageLike.query.filter_by(page_id=page.id, user_id=current_user.id).first()

    if existing_like:
        db.session.delete(existing_like)
    else:
        new_like = PageLike(page_id=page.id, user_id=current_user.id)
        db.session.add(new_like)
    db.session.commit()
    return jsonify(success=True)

@app.route('/shop')
def shop():
    purchased_items = Purchase.query.filter_by(user_id=current_user.id).all()
    purchased_items_names = {p.item_name for p in purchased_items}


    for category, items in items_for_purchase.items():
        for item_name, item_details in items.items():
            if item_name in purchased_items_names or item_details.get('cost', 0) == 0:
                item_details['purchased'] = True
            else:
                item_details['purchased'] = False

    user_purchases_count = Purchase.query.filter_by(user_id=current_user.id).count()
    if user_purchases_count >= 5:
        complete_challenge(current_user, "The Store Spree")

    categories_purchased = {purchase.item_type for purchase in current_user.purchases}
    all_categories = set(items_for_purchase.keys())
    if categories_purchased == all_categories:
        complete_challenge(current_user, "The Eclectic Collector")

    return render_template('shop.html', items_for_purchase=items_for_purchase, sesame_seeds=current_user.sesame_seeds)

@app.route('/comment_page/<uuid>', methods=['POST'])
@login_required
def comment_page(uuid):

    user_commented_pages = PageComment.query.filter_by(user_id=current_user.id).distinct(PageComment.page_id).count()
    if user_commented_pages >= 5:
        complete_challenge(current_user, "The Comment Crusader")

    page = GeneratedPage.query.filter_by(uuid=uuid).first_or_404()
    comment_text = request.form.get('comment')

    sanitized_comment = bleach.clean(comment_text, strip=True)

    if len(sanitized_comment.split()) >= 50:
        complete_challenge(current_user, "The Creative Commentator")

    if sanitized_comment:
        new_comment = PageComment(page_id=page.id, user_id=current_user.id, comment_text=sanitized_comment)
        db.session.add(new_comment)
        current_user.sesame_seeds += 5
        db.session.commit()
        return jsonify(success=True)
    return jsonify(success=False, message="Comment text is required.")

@app.route('/api/completed-challenges/<username>')
@login_required  
def get_completed_challenges(username):
    global challenges
    user_sesame_seeds = current_user.sesame_seeds
    if user_sesame_seeds >= 500 and user_sesame_seeds <= 999:
        complete_challenge(current_user, "The Sesame Seed Collector")

    if user_sesame_seeds >= 1000:
        complete_challenge(current_user, "The Sesame Seed Saver")

    if current_user.generated_pages_count >= 5:
        complete_challenge(current_user, "The Page Prodigy")

    for page in current_user.pages:
        if len(page.comments) >= 5:
            complete_challenge(current_user, "The Feedback Philanthropist")
            break

    user_liked_pages = PageLike.query.filter_by(user_id=current_user.id).count()
    if user_liked_pages >= 10:
        complete_challenge(current_user, "The Social Butterfly")

    for page in current_user.pages:
        if len(page.likes) >= 3:
            complete_challenge(current_user, "The Like Leader")
            break



    user = User.query.filter_by(username=username).first_or_404()
    completed_challenges = CompletedChallenge.query.filter_by(user_id=user.id).all()
    completed_challenge_titles = [challenge.challenge_title for challenge in completed_challenges]

    all_challenges = {ch["title"]: ch for ch in challenges}
    uncompleted_challenges = [{"title": title, "description": all_challenges[title]["description"], "completion_date": None} for title in all_challenges if title not in completed_challenge_titles]

    challenges_json = [
        {
            'user' : username,
            'title': challenge.challenge_title,
            'description': challenge.challenge_description,
            'completion_date': challenge.completion_date.strftime('%Y-%m-%d %H:%M:%S') if challenge.completion_date else None,
            'completed': True
        } for challenge in completed_challenges
    ] + [
        {
            'user' : username,
            'title': challenge['title'],
            'description': challenge['description'],
            'completion_date': challenge['completion_date'],
            'completed': False
        } for challenge in uncompleted_challenges
    ]

    return jsonify(challenges_json)

@app.route('/api/pages')
@login_required
def api_pages():
    try:
        query = request.args.get('query', None)
        pages_query = GeneratedPage.query.filter(GeneratedPage.is_unlisted == False)

        if query:
            like_query = f'%{query}%'
            pages_query = pages_query.filter(db.or_(
                GeneratedPage.user_input.ilike(like_query),
                GeneratedPage.theme.ilike(like_query),
                GeneratedPage.summary.ilike(like_query),
                User.username.ilike(like_query)
            ))

        saved_pages = pages_query.all()

        pages_data = [
            {
                'uuid': page.uuid,
                'mode': page.mode.replace("_"," "),
                'theme': page.theme,
                'user_input': page.user_input,
                'html_content': page.html_content,
                'username': page.user.username,
                'profile_picture': page.user.profile_picture_url,
                'created_at': page.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'summary': page.summary,
                'likes': len(page.likes),
                'comments': [
                    {
                        'profile_image': comment.user.profile_picture_url,
                        'text': comment.comment_text,
                        'user_id': comment.user_id,
                        'username': comment.user.username,
                        'created_at': comment.created_at.isoformat()  
                    } for comment in page.comments
                ]
            } for page in saved_pages
        ]

        return jsonify(pages_data)
    except Exception as e:
        app.logger.error(f"Error loading pages: {str(e)}")
        return jsonify(error="Failed to load pages"), 500

@app.route('/purchase/<item_type>/<item_name>', methods=['POST'])
@login_required
def purchase_item(item_type, item_name):
    current_user_seeds = current_user.sesame_seeds
    try:
        item = items_for_purchase[item_type][item_name]
        if Purchase.query.filter_by(user_id=current_user.id, item_type=item_type, item_name=item_name).first():
            return jsonify(success=False, message="Item already purchased.")
        cost = item.get('cost', 0)
        if cost > current_user_seeds:
            return jsonify(success=False, message="Not enough sesame seeds to purchase.")
        current_user.sesame_seeds -= cost
        if item_type == 'storage':
            extra_pages = item.get('extra_pages', 0)
            current_user.extra_storage += extra_pages
        new_purchase = Purchase(user_id=current_user.id, item_type=item_type, item_name=item_name)
        db.session.add(new_purchase)
        db.session.commit()
        return jsonify(success=True, message=f"{item_name} purchased successfully.")
    except KeyError:
        abort(404)

@app.route('/dev/gain-seeds')
@login_required
def gain_seeds():
    if not app.debug:
        return jsonify(success=False, message="This route is not available."), 403
    current_user.sesame_seeds += 100
    db.session.commit()
    return jsonify(success=True, message="100 sesame seeds added successfully!")

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter(func.lower(User.username) == func.lower(username)).first()
        if user is None or not user.check_password(password):
            flash('Invalid username or password.', 'error')
            time.sleep(1)
            return redirect(url_for('login'))
        login_user(user)
        return redirect(url_for('index'))  
    return render_template("login.html")

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        username = request.form['username']
        reset_string = request.form['reset_string']
        new_password = request.form['new_password']
        user = User.query.filter_by(username=username, reset_string=reset_string).first()
        if user:
            user.set_password(new_password)
            db.session.commit()
            flash('Password succesfully reset', 'error')
        flash('Invalid username or reset string.', 'error')
    return render_template('reset_password.html')

def update_image_urls_in_html(html_content, safe,id):
    soup = BeautifulSoup(html_content, 'html.parser')
    images = soup.find_all('img')
    try:
        user = User.query.get(id)
        for index, img in enumerate(images):
            if index < 2:
                complete_challenge(user, "The Image Seeker")
                original_src = img['src']
                search_query = img.get('alt', original_src)
                new_src = query_valueserpapi(search_query, safe)
                if new_src:
                    img['src'] = new_src
                else:
                    img.decompose()  
            else:
                img.decompose()  
        return str(soup)
    except Exception as e:
        logging.error(f"Error updating image URLs: {e}", exc_info=True)
        return None

def is_url_image(image_url):
    response = requests.head(image_url)
    content_type = response.headers.get('content-type')
    return content_type.startswith('image/') if content_type else False

def get_theme_name_by_description(description):
    for name, details in items_for_purchase['themes'].items():
        if details['description'] == description:
            return name
    return None
	
@app.route('/generate', methods=['POST'])
def generate_and_update():
    data = request.form
    user_input = data['user_input']
    if len(user_input) >= 249 and len(user_input) <= 251 or len(user_input) >= 349 and len(user_input) <= 351:
        complete_challenge(current_user, "The Word Smith")
    description = data['theme']
    visibility = data['page_visibility']
    mode = data['mode']
    if visibility == 'unlisted':
        complete_challenge(current_user, "The Unlisted Uniter")

    safe = data["safe_images"]
    theme = get_theme_name_by_description(description)

    if theme != "silly":
        complete_challenge(current_user, "The Thematic Thinker")

    current_user.generated_pages_count += 1
    current_user.sesame_seeds += 10
    user_sesame_seeds = current_user.sesame_seeds
    db.session.commit()
    complete_challenge(current_user, "The Page Professional")
    app = current_app._get_current_object()  
    with ThreadPoolExecutor() as executor:
        future = executor.submit(generate_html, user_input, theme, safe, current_user.get_id(), mode, app)
        generated_html_content = future.result()
    if generated_html_content:
        if "text-white" in generated_html_content and "bg-white" in generated_html_content:
            complete_challenge(current_user, "The Unreadable")
        elif "background: white" in generated_html_content and "color: white" in generated_html_content:
            complete_challenge(current_user, "The Unreadable")

        if "<script>" in generated_html_content.lower():
            complete_challenge(current_user, "The Code Quest")

        text = BeautifulSoup(generated_html_content, 'html.parser').get_text()
        word_count = len(text.split())
        if word_count >= 250:
            complete_challenge(current_user, "The Art of Articulation")

    complete_challenge(current_user, "The Page Professional")
    return render_template('result.html', generated_html=generated_html_content, user_input=user_input, theme=theme,description=description,visibility=visibility,safe=safe,mode=mode)

def query_image_with_prompt(prompt):
    params = {
        'api_key': '',
        'q': prompt,
        'search_type': 'images',
        'num': 1,
        'safe': 'active'
    }
    response = requests.get('https://api.valueserp.com/search', params=params)
    data = response.json()
    if 'image_results' in data and data['image_results']:
        url_conversion = data["image_results"]
        for attempt in range(2):  
            random_image_info = random.choice(url_conversion)
            image_url = random_image_info["image"]
            response = requests.head(image_url, allow_redirects=True)

            if response.status_code != 404:
                return image_url  
            else:
        	    return None
    else:
        return None

def count_and_parse_files():
    saved_pages = [f for f in os.listdir('static') if f.endswith('.html')]
    timestamps = [datetime.strptime(f[-21:-6], "%Y%m%d_%H%M%S").strftime("%Y-%m-%d %H:%M:%S") for f in saved_pages]
    return len(saved_pages), timestamps

def track_page_generation_count(bool_passed_in):
    count_file = 'page_generation_count.txt'
    count = 0 if not os.path.exists(count_file) else int(open(count_file, 'r').read().strip() or 0)
    if bool_passed_in:
        with open(count_file, 'w') as file:
            file.write(str(count + 1))
    return count

@app.route('/', methods=['GET', 'POST'])
@login_required
def index():

    if request.method == 'POST':
        owned_modes = [p.item_name for p in current_user.purchases if p.item_type == 'modes']
        logging.info("POST request received, processing form data")
        data = request.form
        track_page_generation_count(True)
        logging.info(data)
        try:
            mode  = data["mode"]
        except:
            mode = "regular"
        safe = data["safe_images"]
        user_input = data['user_input']
        theme = data['theme']
        visibility = data['page_visibility']
        return render_template(
            'loading.html',
            user_input=user_input,
            theme=theme,
            visibility=visibility,
            safe=safe,
            mode=mode
        )

    logging.info("GET request received, rendering index page")
    owned_themes = set(p.item_name for p in current_user.purchases if p.item_type == 'themes')
    owned_themes.add('silly')
    owned_modes = set(p.item_name for p in current_user.purchases if p.item_type == 'modes')
    owned_modes.add('regular_mode')
    themes_for_template = [{'name': theme, 'description': items_for_purchase['themes'][theme]['description']} for theme in owned_themes]
    prompt_length = next((items_for_purchase['Prompt Length Increase']['prompt_length']['length'] for p in current_user.purchases if p.item_type == 'Prompt Length Increase'), 250)
    page_generation_count = track_page_generation_count(False)
    try:
        total_files = db.session.query(GeneratedPage).count()
    except:
        total_files = 0
    return render_template(
        'index.html',
        theme_groups=themes_for_template,  
        total_files=total_files,
        page_generation_count=page_generation_count,
        current_username=current_user.username,
        prompt_length=prompt_length,
        sesame_seeds=current_user.sesame_seeds,
        owned_modes=owned_modes
    )

@app.route('/user/<username>')
@login_required
def view_profile(username):
    user = User.query.filter_by(username=username).first_or_404()

    if current_user.username != username:
        pages = user.pages
        pages = [page for page in pages if page.is_unlisted]
    else:
        pages = user.pages


    total_challenges = len(challenges)
    user_completed_challenges = CompletedChallenge.query.filter_by(user_id=user.id).all()
    completed_count = len(user_completed_challenges)

    proudest_achievement = user.proudest_achievement if user.proudest_achievement else "No Achievement chosen"
    initial_quota = 10  # Assuming the initial quota is 10
    total_storage_quota = initial_quota + user.extra_storage
    current_storage_used = len(user.pages)
    isCurrentUser = username == current_user.username
    return jsonify({
        'id': user.id if isCurrentUser else None,  
        'username': user.username,
        'generated_pages_count': user.generated_pages_count,
        'sesame_seeds': user.sesame_seeds,  # Sensitive data guarded
        'current_storage_used': current_storage_used,
        'total_storage_quota': total_storage_quota,
        'username': user.username,
        'total_challenges': total_challenges,
        'completed_challenges_count': completed_count,
        'bio': user.bio if user.bio is not None else f"Hi, I'm {user.username}",
        'profile_picture_url': user.profile_picture_url,
        'proudest_achievement': proudest_achievement,
        'saved_pages': [
            {
                'id': page.id,
                'uuid': page.uuid,
                'theme': page.theme,
                'user_input': page.user_input,
                'created_at': page.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'summary': page.summary,
                'is_unlisted': page.is_unlisted
            } for page in user.pages if not page.is_unlisted or isCurrentUser   
        ],
        'likes_sent': len(user.page_likes),
        'comments_sent': len(user.page_comments)
    })

@app.route('/profile/customize', methods=['POST'])
@login_required
def customize_profile():
    user = current_user 
    bio = request.form.get('bio', None)
    proudest_achievement = request.form.get('proudest_achievement', None)
    prompt = request.form.get('image_search_prompt')
    if bio is not None and len(bio) < 150:
        sanitized_bio = bleach.clean(bio, strip=True)  
        user.bio = sanitized_bio
    if prompt:
        image_url = query_image_with_prompt(prompt)  
        if image_url:
            user.profile_picture_url = image_url
        else:
            flash('No image found for the provided prompt.', 'warning')
            
    else:
        pass

    if proudest_achievement and any(
        challenge.challenge_title == proudest_achievement for challenge in user.completed_challenges):
        user.proudest_achievement = proudest_achievement
    db.session.commit()

    flash('Your profile has been updated.', 'success')
    return redirect(url_for('profile', username=user.username))

@app.route('/profile', defaults={'username': None})
@app.route('/profile/<username>')
@login_required
def profile(username):
    if username is None:
        user = current_user.username
        user = User.query.filter_by(username=current_user.username).first_or_404()
        completed_challenges = CompletedChallenge.query.filter_by(user_id=user.id).all()
        completed_challenge_titles = [challenge.challenge_title for challenge in completed_challenges]
    else:
        user = User.query.filter_by(username=username).first_or_404()
        completed_challenges = CompletedChallenge.query.filter_by(user_id=user.id).all()
        completed_challenge_titles = [challenge.challenge_title for challenge in completed_challenges]
    return render_template('profile.html', user=user, current_username=current_user.username, completed_challenges=completed_challenge_titles)



@app.route('/delete-page/<uuid>', methods=['DELETE'])
@login_required
def delete_page(uuid):
    page = GeneratedPage.query.filter_by(uuid=uuid).first_or_404()
    if page.user_id != current_user.id:
        abort(403) 
    PageLike.query.filter_by(page_id=page.id).delete()  
    PageComment.query.filter_by(page_id=page.id).delete()  
    db.session.delete(page)
    db.session.commit()
    complete_challenge(current_user,"The Page Punisher")
    return jsonify({'message': 'Page deleted successfully.'})


@app.route('/save-page', methods=['POST'])
@login_required
def save_page():
    data = request.json
    page_uuid = str(uuid4())
    initial_quota = 10
    total_storage_allowed = initial_quota + current_user.extra_storage
    current_storage_used = len(current_user.pages)
    is_unlisted = True if data.get('page_visibility') == 'unlisted' else False
    if current_storage_used >= total_storage_allowed:
        return jsonify(status='failure', message='Storage limit reached. Please purchase more storage to save new pages.')
    def generate_summary_with_openai(html_content):
        inputs = load_inputs()
        response = openai.Completion.create(
            engine=inputs['engines']['default_engine'],
            prompt=f"Summarize this HTML page simply by it's content do not mention specific elements make sure it is short and concise: {html_content}",
            max_tokens=inputs['tokens']['summary_token_size'],
            temperature=inputs['parameters']['temperature'],
            top_p=inputs['parameters']['top_p']
        )
        summary = response['choices'][0]['text'].strip().strip('"')
        return summary
    summary = generate_summary_with_openai(data['html_content'])
    new_page = GeneratedPage(
        uuid=page_uuid,
        theme=data['theme'],
        user_input=data['user_input'],
        html_content=data['html_content'],
        summary=summary,
        user_id=current_user.id,
        is_unlisted=is_unlisted,
    	mode=data["mode"]
    )
    db.session.add(new_page)
    current_user.sesame_seeds += 15
    db.session.commit()

    if len(current_user.pages) >= 10:
        complete_challenge(current_user, "The Prolific Publisher")

    return jsonify(status='success', page_id=page_uuid)

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
        top_p=inputs['parameters']['top_p'] 
    )
    return jsonify({"name": response.choices[0].text.strip().strip('"')})

@app.route('/leaderboard')
def leaderboard():
    return render_template('leaderboard.html')

@app.route('/leaderboard/api')
def leaderboard_api():
    search_username = request.args.get("username", "").strip().lower()

    subquery_likes = db.session.query(
        GeneratedPage.user_id,
        func.count(PageLike.id).label('likes_count')
    ).join(PageLike, GeneratedPage.id == PageLike.page_id
    ).filter(GeneratedPage.user_id != PageLike.user_id
    ).group_by(GeneratedPage.user_id).subquery()

    subquery_comments = db.session.query(
        GeneratedPage.user_id,
        func.count(PageComment.id).label('comments_count')
    ).join(PageComment, GeneratedPage.id == PageComment.page_id
    ).filter(GeneratedPage.user_id != PageComment.user_id
    ).group_by(GeneratedPage.user_id).subquery()

    subquery_saved_pages = db.session.query(
        GeneratedPage.user_id,
        func.count('*').label('saved_pages_count')
    ).group_by(GeneratedPage.user_id).subquery()

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

    if search_username:
        final_query = db.session.query(rank_query).filter(func.lower(rank_query.c.username).like(f"%{search_username}%"))
        total_results = final_query.count()
    else:
        final_query = db.session.query(rank_query)
        total_results = final_query.count()

    users = final_query.limit(10).all()
    leaderboard = [{
        "rank": user.rank,
        "username": user.username,
        "profile_picture_url": user.profile_picture_url,
        "generated_pages": user.generated_pages_count,
        "saved_pages": user.saved_pages,
        "likes_received": user.likes_received,
        "comments_received": user.comments_received,
        "sesame_seeds": user.sesame_seeds,
        "total_results": total_results 
    } for user in users]

    return jsonify(leaderboard)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0',threaded=True, port=80,debug=True)
