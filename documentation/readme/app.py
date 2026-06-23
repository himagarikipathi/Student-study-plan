import os
from datetime import datetime, date, timedelta
from flask import Flask, render_template, redirect, url_for, flash, request, jsonify, make_response, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, current_user, logout_user, login_required
from flask_bcrypt import Bcrypt
import csv
from io import StringIO
from werkzeug.utils import secure_filename

from models import db, User, Subject, Task, Note, Material
from forms import RegistrationForm, LoginForm, SubjectForm, NoteForm, MaterialForm
from utils import generate_timetable_for_user

app = Flask(__name__)
# Used a simple secret key, change for prod
app.config['SECRET_KEY'] = '5791628bb0b13ce0c676dfde280ba245'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static/uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db.init_app(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route("/")
@app.route("/home")
def home():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('home.html')

@app.route("/register", methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    form = RegistrationForm()
    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        user = User(username=form.username.data, email=form.email.data, password=hashed_password)
        db.session.add(user)
        db.session.commit()
        flash('Account created! You can now log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', title='Register', form=form)

@app.route("/login", methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and bcrypt.check_password_hash(user.password, form.password.data):
            login_user(user, remember=form.remember.data)
            flash('Login Successful!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('dashboard'))
        else:
            flash('Login Unsuccessful. Please check email and password', 'danger')
    return render_template('login.html', title='Login', form=form)

@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for('home'))

@app.route("/dashboard")
@login_required
def dashboard():
    subjects = Subject.query.filter_by(user_id=current_user.id).all()
    today = datetime.now().date()
    daily_tasks = Task.query.filter_by(user_id=current_user.id, date=today).all()
    
    total_tasks = Task.query.filter_by(user_id=current_user.id).count()
    completed_tasks = Task.query.filter_by(user_id=current_user.id, status='Completed').count()
    progress = 0
    if total_tasks > 0:
        progress = int((completed_tasks / total_tasks) * 100)
    
    return render_template('dashboard.html', subjects=subjects, tasks=daily_tasks, progress=progress, int=int)

@app.route("/subjects", methods=['GET', 'POST'])
@login_required
def subjects():
    form = SubjectForm()
    if form.validate_on_submit():
        subject = Subject(name=form.name.data, difficulty=form.difficulty.data,
                          deadline=form.deadline.data, hours_required=form.hours_required.data,
                          user_id=current_user.id)
        db.session.add(subject)
        db.session.commit()
        flash('Subject has been added!', 'success')
        generate_timetable_for_user(current_user)
        return redirect(url_for('subjects'))
    
    subjects_list = Subject.query.filter_by(user_id=current_user.id).all()
    return render_template('subjects.html', title='Subjects', form=form, subjects=subjects_list)

@app.route("/subject/<int:subject_id>/delete", methods=['POST'])
@login_required
def delete_subject(subject_id):
    subject = Subject.query.get_or_404(subject_id)
    if subject.user_id != current_user.id:
        abort(403)
    # delete associated tasks and notes
    Task.query.filter_by(subject_id=subject.id).delete()
    Note.query.filter_by(subject_id=subject.id).delete()
    db.session.delete(subject)
    db.session.commit()
    flash('Subject has been deleted!', 'success')
    generate_timetable_for_user(current_user)
    return redirect(url_for('subjects'))

@app.route("/timetable")
@login_required
def timetable():
    # Show upcoming 7 days
    today = datetime.now().date()
    dates = [today + timedelta(days=i) for i in range(7)]
    
    timetable_data = {}
    for d in dates:
        tasks = Task.query.filter_by(user_id=current_user.id, date=d).all()
        timetable_data[d] = tasks

    return render_template('timetable.html', title='Smart Timetable', timetable_data=timetable_data)

@app.route("/daily")
@login_required
def daily_planner():
    today = datetime.now().date()
    tasks = Task.query.filter_by(user_id=current_user.id, date=today).all()
    return render_template('daily_planner.html', title='Daily Planner', tasks=tasks)

@app.route("/task/<int:task_id>/toggle", methods=['POST'])
@login_required
def toggle_task(task_id):
    task = Task.query.get_or_404(task_id)
    if task.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    task.status = 'Completed' if task.status == 'Pending' else 'Pending'
    db.session.commit()
    return jsonify({'success': True, 'new_status': task.status})

@app.route("/progress")
@login_required
def progress():
    subjects = Subject.query.filter_by(user_id=current_user.id).all()
    subject_stats = []
    
    for sub in subjects:
        total = Task.query.filter_by(subject_id=sub.id).count()
        completed = Task.query.filter_by(subject_id=sub.id, status='Completed').count()
        pct = (completed / total * 100) if total > 0 else 0
        subject_stats.append({
            'name': sub.name,
            'total': total,
            'completed': completed,
            'percent': int(pct)
        })
        
    return render_template('progress.html', title='Progress Tracker', stats=subject_stats)

@app.route("/focus")
@login_required
def focus_mode():
    return render_template('focus.html', title='Focus Mode')

@app.route("/notes", methods=['GET', 'POST'])
@login_required
def notes():
    form = NoteForm()
    material_form = MaterialForm()
    
    subjects = Subject.query.filter_by(user_id=current_user.id).all()
    form.subject_id.choices = [(s.id, s.name) for s in subjects]
    material_form.subject_id.choices = [(s.id, s.name) for s in subjects]
    
    if form.validate_on_submit():
        note = Note(content=form.content.data, subject_id=form.subject_id.data, user_id=current_user.id)
        db.session.add(note)
        db.session.commit()
        flash('Note added!', 'success')
        return redirect(url_for('notes'))
        
    all_notes = Note.query.filter_by(user_id=current_user.id).order_by(Note.created_at.desc()).all()
    all_materials = Material.query.filter_by(user_id=current_user.id).order_by(Material.uploaded_at.desc()).all()
    
    return render_template('notes.html', title='Notes & Materials', form=form, material_form=material_form, notes=all_notes, materials=all_materials)

@app.route("/upload_material", methods=['POST'])
@login_required
def upload_material():
    material_form = MaterialForm()
    subjects = Subject.query.filter_by(user_id=current_user.id).all()
    material_form.subject_id.choices = [(s.id, s.name) for s in subjects]
    
    if material_form.validate_on_submit():
        file = material_form.file.data
        if file:
            filename = secure_filename(file.filename)
            unique_filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            file.save(file_path)
            
            material = Material(filename=filename, filepath=unique_filename, subject_id=material_form.subject_id.data, user_id=current_user.id)
            db.session.add(material)
            db.session.commit()
            flash('Material uploaded successfully!', 'success')
        else:
            flash('Invalid file!', 'danger')
    return redirect(url_for('notes'))

@app.route("/download_material/<int:material_id>")
@login_required
def download_material(material_id):
    material = Material.query.get_or_404(material_id)
    if material.user_id != current_user.id:
        return "Unauthorized", 403
    return send_from_directory(app.config['UPLOAD_FOLDER'], material.filepath, as_attachment=True, download_name=material.filename)

@app.route("/export")
@login_required
def export_timetable():
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['Date', 'Task Title', 'Status', 'Subject'])
    
    tasks = Task.query.filter_by(user_id=current_user.id).order_by(Task.date.asc()).all()
    for task in tasks:
        subj_name = task.subject.name if task.subject else "N/A"
        cw.writerow([task.date, task.title, task.status, subj_name])
        
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=timetable.csv"
    output.headers["Content-type"] = "text/csv"
    return output

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5000)
