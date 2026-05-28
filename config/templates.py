from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class TemplateDefinition:
    id: str
    subject_template: str
    body_template: str
    required_fields: List[str]
    # Only acknowledgment is safe to auto-send; all others require founder review
    auto_send_eligible: bool = False


TEMPLATES: dict[str, TemplateDefinition] = {
    t.id: t
    for t in [
        TemplateDefinition(
            id="initial-outreach",
            subject_template="Engineering Role — {role}",
            body_template=(
                "Hi {candidate_name},\n\n"
                "I came across your work and think you'd be a strong fit for a {role} "
                "role we're building toward.\n\n"
                "{personal_note}\n\n"
                "Would you be open to learning more? Happy to share details if so.\n\n"
                "Best,\n{sender_name}"
            ),
            required_fields=["candidate_name", "role", "personal_note", "sender_name"],
        ),
        TemplateDefinition(
            id="acknowledgment",
            subject_template="Re: {original_subject}",
            body_template=(
                "Hi {candidate_name},\n\n"
                "Thanks for reaching out — we received your message and will follow up shortly.\n\n"
                "Best,\n{sender_name}"
            ),
            required_fields=["candidate_name", "original_subject", "sender_name"],
            auto_send_eligible=True,
        ),
        TemplateDefinition(
            id="answer-common-question",
            subject_template="Re: {original_subject}",
            body_template=(
                "Hi {candidate_name},\n\n"
                "{answer}\n\n"
                "Let us know if you have any other questions.\n\n"
                "Best,\n{sender_name}"
            ),
            required_fields=["candidate_name", "original_subject", "answer", "sender_name"],
            # extra_context expected: question_text (the candidate's actual question)
            # The LLM fills {answer} based on question_text
        ),
        TemplateDefinition(
            id="task-assignment-cover",
            subject_template="Engineering Problem — Next Steps",
            body_template=(
                "Hi {candidate_name},\n\n"
                "Here's the engineering problem we'd like you to work through:\n\n"
                "{task_brief}\n\n"
                "We've set up a private GitHub repository for your submission:\n"
                "{repo_url}\n\n"
                "Push your solution to the main branch of that repository when you're ready. "
                "We'll be notified automatically once you push.\n\n"
                "Best,\n{sender_name}"
            ),
            required_fields=["candidate_name", "task_brief", "repo_url", "sender_name"],
        ),
        TemplateDefinition(
            id="feedback-delivery",
            subject_template="Feedback on Your Submission",
            body_template=(
                "Hi {candidate_name},\n\n"
                "Thank you for your submission. Here's our feedback:\n\n"
                "{feedback}\n\n"
                "{upgrade_ask}\n\n"
                "Best,\n{sender_name}"
            ),
            required_fields=["candidate_name", "feedback", "upgrade_ask", "sender_name"],
        ),
        TemplateDefinition(
            id="request-submission-url",
            subject_template="Re: {original_subject}",
            body_template=(
                "Hi {candidate_name},\n\n"
                "Thanks for your message. It looks like you may be sharing your submission — "
                "could you include the full GitHub repository URL? "
                "Something like: https://github.com/your-username/your-repo\n\n"
                "Once we have the link we'll take a look right away.\n\n"
                "Best,\n{sender_name}"
            ),
            required_fields=["candidate_name", "original_subject", "sender_name"],
            auto_send_eligible=True,
        ),
        TemplateDefinition(
            id="background-request",
            subject_template="Re: {original_subject}",
            body_template=(
                "Hi {candidate_name},\n\n"
                "Great to hear you're interested! To match you to the right opening and tailor "
                "the technical challenge, could you paste your CV or resume directly into this email?\n\n"
                "We'll need:\n"
                "- Your experience and what you've shipped recently\n"
                "- Core skills and tech stack\n"
                "- Current location\n"
                "- Notice period (if employed)\n\n"
                "Just paste it as text — no attachments needed. Once we have it we'll come back "
                "to you with the roles we think fit best.\n\n"
                "Best,\n{sender_name}"
            ),
            required_fields=["candidate_name", "original_subject", "sender_name"],
            auto_send_eligible=True,
        ),
        TemplateDefinition(
            id="profile-incomplete",
            subject_template="Re: {original_subject}",
            body_template=(
                "Hi {candidate_name},\n\n"
                "Thanks for getting back to us! To move forward we still need a bit more detail.\n\n"
                "Could you help us with:\n"
                "{missing_details}\n\n"
                "Once we have that we can match you to the right opening and share the details.\n\n"
                "Best,\n{sender_name}"
            ),
            required_fields=["candidate_name", "original_subject", "missing_details", "sender_name"],
            auto_send_eligible=True,
        ),
        TemplateDefinition(
            id="jd-sharing",
            subject_template="Roles at CureForge — We Think You'd Be a Fit",
            body_template=(
                "Hi {candidate_name},\n\n"
                "Based on your background, here are the roles we think you'd be a strong match for:\n\n"
                "{jd_list}\n\n"
                "Would you like to proceed with any of these? Just reply with the role you're "
                "most interested in and we'll kick off the next step — a short technical problem "
                "tailored to that position.\n\n"
                "Best,\n{sender_name}"
            ),
            required_fields=["candidate_name", "jd_list", "sender_name"],
            auto_send_eligible=True,
        ),
        TemplateDefinition(
            id="warm-hold",
            subject_template="Staying in Touch",
            body_template=(
                "Hi {candidate_name},\n\n"
                "Thank you for the time you've invested in our process. "
                "We'd like to keep you in mind as our needs evolve.\n\n"
                "We'll be in touch.\n\n"
                "Best,\n{sender_name}"
            ),
            required_fields=["candidate_name", "sender_name"],
        ),
        TemplateDefinition(
            id="offer-cover",
            subject_template="An Offer",
            body_template=(
                "Hi {candidate_name},\n\n"
                "We're excited to move forward and extend the following offer:\n\n"
                "{offer_details}\n\n"
                "Please let us know if you have any questions.\n\n"
                "Best,\n{sender_name}"
            ),
            required_fields=["candidate_name", "offer_details", "sender_name"],
        ),
    ]
}
