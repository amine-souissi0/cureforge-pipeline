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
        ),
        TemplateDefinition(
            id="task-assignment-cover",
            subject_template="Engineering Problem — Next Steps",
            body_template=(
                "Hi {candidate_name},\n\n"
                "Here's the engineering problem we'd like you to work through:\n\n"
                "{task_brief}\n\n"
                "Please submit your work by replying to this email with a link to your "
                "GitHub repository.\n\n"
                "Best,\n{sender_name}"
            ),
            required_fields=["candidate_name", "task_brief", "sender_name"],
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
