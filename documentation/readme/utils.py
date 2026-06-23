from datetime import datetime, timedelta
from models import db, Task, Subject

def generate_timetable_for_user(user):
    # This deletes all pending auto-generated study tasks from today onwards,
    # and recreates them based on current subjects and remaining workload.
    
    today = datetime.now().date()
    # Delete existing pending non-exam tasks from today onwards
    Task.query.filter(Task.user_id == user.id, Task.is_exam == False, Task.status == 'Pending', Task.date >= today).delete()
    db.session.commit()

    # Recalculate and generate new tasks
    subjects = Subject.query.filter_by(user_id=user.id).all()
    
    for subject in subjects:
        if subject.deadline < today:
            continue
        
        # Calculate how many hours are completed or remaining
        completed_tasks_count = Task.query.filter_by(subject_id=subject.id, status='Completed').count()
        # Assume each task is 1 hour of study
        remaining_hours = subject.hours_required - completed_tasks_count
        if remaining_hours <= 0:
            continue
        
        days_remaining = (subject.deadline - today).days
        if days_remaining <= 0:
            days_remaining = 1 # Force remaining hours to be done today
        
        hours_per_day = remaining_hours / days_remaining
        # Distribute hours. Here we will use a simple integer rounding approach.
        # e.g., if total 5 hours over 2 days, 3 hours day 1, 2 hours day 2.
        
        distributed_hours = [int(hours_per_day)] * days_remaining
        remainder = int(remaining_hours - sum(distributed_hours))
        
        # distribute remainder
        for i in range(remainder):
            distributed_hours[i % days_remaining] += 1
            
        # Create new tasks
        for day_offset, hours in enumerate(distributed_hours):
            if hours <= 0:
                continue
            task_date = today + timedelta(days=day_offset)
            # Create a task for each hour (so user can check off hour by hour)
            for _ in range(int(hours)):
                # Adjusting task title based on difficulty
                difficulty_label = f"[{subject.difficulty}] "
                new_task = Task(
                    title=f"{difficulty_label}Study Session: {subject.name}",
                    date=task_date,
                    status='Pending',
                    is_exam=False,
                    user_id=user.id,
                    subject_id=subject.id
                )
                db.session.add(new_task)
    
    db.session.commit()
