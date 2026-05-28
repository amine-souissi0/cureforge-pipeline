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
            subject_template="{role} — LongevityInTime",
            body_template=(
                "Hi {candidate_name},\n\n"
                "I came across your work and wanted to reach out directly.\n\n"
                "I'm building the engineering team at LongevityInTime — we're working on the data "
                "and AI infrastructure that powers longevity science. Our platform ingests and "
                "processes millions of biomarker measurements to help researchers understand "
                "what drives healthy human aging.\n\n"
                "{personal_note}\n\n"
                "We're looking for a {role} who cares about building reliable, well-engineered "
                "systems in a domain where the work genuinely matters.\n\n"
                "Would you be open to a quick conversation? Happy to share more about the role "
                "and what we're building.\n\n"
                "Best,\n{sender_name}"
            ),
            required_fields=["candidate_name", "role", "personal_note", "sender_name"],
        ),
        TemplateDefinition(
            id="acknowledgment",
            subject_template="Re: {original_subject}",
            body_template=(
                "Hi {candidate_name},\n\n"
                "Thanks for getting in touch — we received your message and will follow up shortly.\n\n"
                "Best,\n{sender_name}\n"
                "LongevityInTime"
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
            subject_template="LongevityInTime — Engineering Problem",
            body_template=(
                "Hi {candidate_name},\n\n"
                "Here's the engineering problem we'd like you to work through.\n\n"
                "This is representative of the kind of work you'd own at LongevityInTime — "
                "building reliable, well-structured systems that process and validate "
                "data with precision.\n\n"
                "{task_brief}\n\n"
                "When you're ready to submit:\n"
                "1. Push your solution to a public GitHub repository\n"
                "2. Reply to this email with the GitHub URL\n\n"
                "Take the time you need — we value correctness and clarity over speed.\n\n"
                "Best,\n{sender_name}\n"
                "LongevityInTime"
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
                "Great to hear you're interested in LongevityInTime!\n\n"
                "We're building the engineering team behind our longevity research platform — "
                "the infrastructure that processes biomarker data, runs predictive models, and "
                "helps scientists understand what drives healthy human aging.\n\n"
                "To match you to the right role and tailor the technical challenge to your background, "
                "please share your CV or resume.\n\n"
                "You can either:\n"
                "- Reply with your CV pasted as text, or\n"
                "- Attach your resume as a PDF or Word document\n\n"
                "It would help to know:\n"
                "- Your recent experience and what you've shipped\n"
                "- Core skills and tech stack\n"
                "- Current location\n"
                "- Notice period (if currently employed)\n\n"
                "Once we have that, we'll come back to you with the roles we think are the best fit.\n\n"
                "Best,\n{sender_name}\n"
                "LongevityInTime"
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
            subject_template="Open Roles at LongevityInTime — Strong Match for Your Background",
            body_template=(
                "Hi {candidate_name},\n\n"
                "Thanks for sharing your background. Based on what you've built and your experience, "
                "here are the LongevityInTime roles we think you'd be a strong fit for:\n\n"
                "{jd_list}\n\n"
                "LongevityInTime is building the data and AI infrastructure for longevity science — "
                "the platform our researchers use to track biomarkers, run predictive models, "
                "and understand what drives healthy aging at scale.\n\n"
                "If any of these roles interest you, just reply with the one you'd like to pursue "
                "and we'll send over a short technical problem tailored to that position.\n\n"
                "Best,\n{sender_name}\n"
                "LongevityInTime"
            ),
            required_fields=["candidate_name", "jd_list", "sender_name"],
            auto_send_eligible=True,
        ),
        TemplateDefinition(
            id="warm-hold",
            subject_template="LongevityInTime — Thank You",
            body_template=(
                "Hi {candidate_name},\n\n"
                "Thank you for the time and effort you've put into our process — "
                "we genuinely appreciate it.\n\n"
                "We're not moving forward at this stage, but we'd like to keep you in mind "
                "as LongevityInTime grows. The longevity space is moving fast and our engineering "
                "needs are evolving — we may well be in touch.\n\n"
                "Thanks again, and best of luck with what you're working on.\n\n"
                "Best,\n{sender_name}\n"
                "LongevityInTime"
            ),
            required_fields=["candidate_name", "sender_name"],
        ),
        TemplateDefinition(
            id="offer-cover",
            subject_template="LongevityInTime — Offer",
            body_template=(
                "Hi {candidate_name},\n\n"
                "We're excited to move forward and would love to have you join LongevityInTime.\n\n"
                "Here are the details of our offer:\n\n"
                "{offer_details}\n\n"
                "We're building something genuinely important — the engineering infrastructure "
                "that powers longevity research — and we think you'd be a great part of that.\n\n"
                "Please take the time you need to review. We're happy to answer any questions.\n\n"
                "Best,\n{sender_name}\n"
                "LongevityInTime"
            ),
            required_fields=["candidate_name", "offer_details", "sender_name"],
        ),
    ]
}
