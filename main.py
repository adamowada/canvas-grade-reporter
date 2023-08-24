from datetime import datetime, timedelta
import pytz
import os
import requests
import textwrap
from dotenv import load_dotenv
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


# Load environment variables
load_dotenv()

access_token = os.getenv("ACCESS_TOKEN")
domain = os.getenv("CANVAS_DOMAIN")  # e.g. 'canvas.instructure.com'
course_ids = os.getenv("COURSE_IDS").split(",")  # Expects comma-separated values

headers = {
    "Authorization": "Bearer " + access_token,
}


def process_course(course_id):
    print(course_id)
    url = f"https://{domain}/api/v1/courses/{course_id}/assignments"
    assignments_to_grade = []

    while url:
        # Make the API request
        response = requests.get(url, headers=headers)

        # Check the response status
        if response.status_code == 200:
            # Parse the response as JSON
            assignments = response.json()

            # Go through each assignment
            for assignment in assignments:
                # Check if it needs grading
                if assignment["needs_grading_count"] > 0:
                    # Get the submissions for this assignment
                    sub_url = f'https://{domain}/api/v1/courses/{course_id}/assignments/{assignment["id"]}/submissions?include[]=user'
                    sub_response = requests.get(sub_url, headers=headers)

                    # Check the response status
                    if sub_response.status_code == 200:
                        # Parse the response as JSON
                        submissions = sub_response.json()

                        for submission in submissions:
                            # Check if the submission has been graded
                            if (
                                submission["graded_at"] is None
                                and submission["submitted_at"] is not None
                            ):
                                # Convert the submission timestamp to a datetime object
                                submitted_at = datetime.strptime(
                                    submission["submitted_at"], "%Y-%m-%dT%H:%M:%SZ"
                                )

                                # Assuming the timestamp is in UTC, localize it
                                utc_zone = pytz.timezone('UTC')
                                localized_timestamp = utc_zone.localize(submitted_at)

                                # Convert to PST
                                pst_zone = pytz.timezone('America/Los_Angeles')
                                submitted_at_pst = localized_timestamp.astimezone(pst_zone)

                                # Get the current time in PST
                                current_time_pst = datetime.now(pst_zone)

                                # Check if it has been more than 24 hours since the assignment was submitted
                                if submitted_at_pst < current_time_pst - timedelta(days=1):
                                    # print("submission is:", submission)
                                    assignments_to_grade.append(
                                        {
                                            "Assignment Name": assignment["name"],
                                            "Student Name": submission["user"]["name"],
                                            "Submitted At": submitted_at_pst,
                                        }
                                    )
                    else:
                        print(f"Error getting submissions: {sub_response.status_code}")

            # Get the next page link if it exists
            links = requests.utils.parse_header_links(
                response.headers["Link"].rstrip(">").replace(">,<", ",<")
            )
            url = None
            for link in links:
                if link["rel"] == "next":
                    url = link["url"]
                    break

        else:
            print(f"Error: {response.status_code}")
            break

    return assignments_to_grade


def save_to_pdf(assignments_list, filename="assignments.pdf"):
    my_canvas = canvas.Canvas(filename, pagesize=letter)
    width, height = letter
    height = height - 50  # leave some margin

    for course, assignments in assignments_list:
        my_canvas.setFont("Helvetica", 12)
        my_canvas.drawString(50, height, f"Course ID: {course}")
        height = height - 30  # new line

        for assignment in assignments:
            assignment_name = assignment["Assignment Name"]
            student_name = assignment["Student Name"]
            submitted_at = assignment["Submitted At"]

            line = f"Assignment Name: {assignment_name}, Student Name: {student_name}, Submitted At: {submitted_at}"
            wrapped_text = textwrap.fill(line, width=80)
            lines = wrapped_text.split("\n")

            for line in lines:
                my_canvas.drawString(50, height, line)
                height = height - 20  # new line

                # if space is less, start a new page
                if height <= 50:
                    my_canvas.showPage()  # save the current page
                    my_canvas.setFont("Helvetica", 12)
                    height = letter[1] - 50  # start from top again

            height = height - 10  # new line

        if not assignments:
            my_canvas.drawString(50, height, "Grades are caught up!")
            height = height - 20  # new line

        height = height - 40  # leave some space between courses

        # if space is less, start a new page
        if height <= 50:
            my_canvas.showPage()  # save the current page
            my_canvas.setFont("Helvetica", 12)
            height = letter[1] - 50  # start from top again

    my_canvas.showPage()  # save the final page
    my_canvas.save()  # save the pdf


def main():
    all_assignments = []
    for course_id in course_ids:
        course_name = requests.get(
            f"https://{domain}/api/v1/courses/{course_id}", headers=headers
        ).json()["name"]
        assignments = process_course(course_id)
        all_assignments.append((course_name, assignments))

    save_to_pdf(all_assignments, f"grade_report_{datetime.now()}.pdf")


if __name__ == "__main__":
    main()
    print("Reporting complete.")
