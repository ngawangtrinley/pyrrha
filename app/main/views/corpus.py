from flask import request, jsonify, flash, redirect, url_for, abort, current_app
from flask_login import current_user, login_required
import sqlalchemy.exc


from app import db
from app.models.linguistic import CorpusUser, ControlLists
from .utils import render_template_with_nav_info, format_api_like_reply, create_input_format_convertion
from .. import main
from ...utils.forms import strip_or_none
from ...models import Corpus, WordToken

AUTOCOMPLETE_LIMIT = 20


@main.route('/corpus/new', methods=["POST", "GET"])
@login_required
def corpus_new():
    """ Register a new corpus
    """
    lemmatizers = current_app.config.get("LEMMATIZERS", [])
    if request.method == "POST":
        if not current_user.is_authenticated:
            abort(403)
        elif not len(strip_or_none(request.form.get("name", ""))):
            flash("You forgot to give a name to your corpus", category="error")
            return render_template_with_nav_info(
                'main/corpus_new.html',
                lemmatizers=lemmatizers,
                tsv=request.form.get("tsv")
            )
        else:
            tokens, allowed_lemma, allowed_morph, allowed_POS = create_input_format_convertion(
                request.form.get("tsv"),
                request.form.get("allowed_lemma", None),
                request.form.get("allowed_morph", None),
                request.form.get("allowed_POS", None)
            )
            try:
                corpus = Corpus.create(
                    request.form.get("name"),
                    word_tokens_dict=tokens,
                    allowed_lemma=allowed_lemma,
                    allowed_POS=allowed_POS,
                    allowed_morph=allowed_morph,
                    context_left=request.form.get("context_left", None),
                    context_right=request.form.get("context_right", None)
                )
                db.session.add(CorpusUser(corpus=corpus, user=current_user, is_owner=True))
                ControlLists.link(corpus=corpus, user=current_user, is_owner=True)
                db.session.commit()
                flash("New corpus registered", category="success")
                return redirect(url_for(".corpus_get", corpus_id=corpus.id))
            except sqlalchemy.exc.StatementError as e:
                db.session.rollback()
                flash("The corpus cannot be registered. Check your data", category="error")
                if str(e.orig) == "UNIQUE constraint failed: corpus.name":
                    flash("You have already a corpus going by the name {}".format(request.form.get("name")),
                          category="error")
                return render_template_with_nav_info(
                    'main/corpus_new.html',
                    lemmatizers=lemmatizers,
                    tsv=request.form.get("tsv")
                )
            except ValueError as e:
                db.session.rollback()
                flash(str(e), category="error")
                return render_template_with_nav_info(
                    'main/corpus_new.html',
                    lemmatizers=lemmatizers,
                    tsv=request.form.get("tsv")
                )
            except Exception as e:
                db.session.rollback()
                print(e)
                flash("The corpus cannot be registered. Check your data", category="error")
                return render_template_with_nav_info(
                    'main/corpus_new.html',
                    lemmatizers=lemmatizers,
                    tsv=request.form.get("tsv")
                )

    return render_template_with_nav_info('main/corpus_new.html', lemmatizers=lemmatizers)


@main.route('/corpus/get/<int:corpus_id>')
@login_required
def corpus_get(corpus_id):
    """ Read information about the corpus

    :param corpus_id: ID of the corpus
    :return:
    """
    corpus = Corpus.query.get_or_404(corpus_id)
    if not corpus.has_access(current_user):
        abort(403)
    return render_template_with_nav_info('main/corpus_info.html', corpus=corpus)


@main.route('/corpus/<int:corpus_id>/api/<allowed_type>')
def corpus_allowed_values_api(corpus_id, allowed_type):
    """ Find allowed values

    :param corpus_id: Id of the corpus
    :param allowed_type: Type of allowed value (lemma, morph, POS)
    """
    corpus = Corpus.query.get_or_404(corpus_id)
    allowed_list = corpus.get_allowed_values(allowed_type=allowed_type).count() > 0
    filter_id = corpus.id
    if allowed_list:
        filter_id = corpus.control_lists_id
    return jsonify(
        [
            format_api_like_reply(result, allowed_type)
            for result in WordToken.get_like(
                filter_id=filter_id,
                form=request.args.get("form"),
                group_by=True,
                type_like=allowed_type,
                allowed_list=allowed_list
            ).limit(AUTOCOMPLETE_LIMIT)
            if result is not None
        ]
    )


@main.route('/corpus/<int:corpus_id>/fixtures')
def generate_fixtures(corpus_id):
    corpus = Corpus.query.get_or_404(corpus_id)
    if not corpus.has_access(current_user):
        abort(403)
    tokens = corpus.get_tokens().all()
    allowed_lemma = corpus.get_allowed_values(allowed_type="lemma")
    allowed_POS = corpus.get_allowed_values(allowed_type="POS")
    return render_template_with_nav_info(
        template="main/corpus_generate_fixtures.html", tokens=tokens,
        allowed_lemma=allowed_lemma, allowed_pos=allowed_POS
    )
