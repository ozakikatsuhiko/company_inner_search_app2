"""
このファイルは、最初の画面読み込み時にのみ実行される初期化処理が記述されたファイルです。
"""

############################################################
# ライブラリの読み込み
############################################################
import os
import logging
from logging.handlers import TimedRotatingFileHandler
from uuid import uuid4
import sys
import unicodedata
from dotenv import load_dotenv
import streamlit as st
from docx import Document
from langchain_community.document_loaders import WebBaseLoader
from langchain.text_splitter import CharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import Chroma
import constants as ct


############################################################
# 設定関連
############################################################
# 「.env」ファイルで定義した環境変数の読み込み
# 現在のファイルと同じディレクトリの.envファイルを明示的に指定
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path)

# 環境変数の読み込み確認
import logging
temp_logger = logging.getLogger('temp')
if os.getenv("OPENAI_API_KEY"):
    temp_logger.info(f"OPENAI_API_KEY loaded from {dotenv_path}")
else:
    temp_logger.warning(f"OPENAI_API_KEY not found. Checking .env file at {dotenv_path}")
    if os.path.exists(dotenv_path):
        temp_logger.info(f".env file exists at {dotenv_path}")
    else:
        temp_logger.error(f".env file not found at {dotenv_path}")


############################################################
# 関数定義
############################################################

def initialize():
    """
    画面読み込み時に実行する初期化処理
    """
    # 初期化データの用意
    initialize_session_state()
    # ログ出力用にセッションIDを生成
    initialize_session_id()
    # ログ出力の設定
    initialize_logger()
    # RAGのRetrieverを作成
    initialize_retriever()


def initialize_logger():
    """
    ログ出力の設定
    """
    # 指定のログフォルダが存在すれば読み込み、存在しなければ新規作成
    os.makedirs(ct.LOG_DIR_PATH, exist_ok=True)
    
    # 引数に指定した名前のロガー（ログを記録するオブジェクト）を取得
    # 再度別の箇所で呼び出した場合、すでに同じ名前のロガーが存在していれば読み込む
    logger = logging.getLogger(ct.LOGGER_NAME)

    # すでにロガーにハンドラー（ログの出力先を制御するもの）が設定されている場合、同じログ出力が複数回行われないよう処理を中断する
    if logger.hasHandlers():
        return

    # 1日単位でログファイルの中身をリセットし、切り替える設定
    log_handler = TimedRotatingFileHandler(
        os.path.join(ct.LOG_DIR_PATH, ct.LOG_FILE),
        when="D",
        encoding="utf8"
    )
    # 出力するログメッセージのフォーマット定義
    # - 「levelname」: ログの重要度（INFO, WARNING, ERRORなど）
    # - 「asctime」: ログのタイムスタンプ（いつ記録されたか）
    # - 「lineno」: ログが出力されたファイルの行番号
    # - 「funcName」: ログが出力された関数名
    # - 「session_id」: セッションID（誰のアプリ操作か分かるように）
    # - 「message」: ログメッセージ
    formatter = logging.Formatter(
        f"[%(levelname)s] %(asctime)s line %(lineno)s, in %(funcName)s, session_id={st.session_state.session_id}: %(message)s"
    )

    # 定義したフォーマッターの適用
    log_handler.setFormatter(formatter)

    # ログレベルを「INFO」に設定
    logger.setLevel(logging.INFO)

    # 作成したハンドラー（ログ出力先を制御するオブジェクト）を、
    # ロガー（ログメッセージを実際に生成するオブジェクト）に追加してログ出力の最終設定
    logger.addHandler(log_handler)


def initialize_session_id():
    """
    セッションIDの作成
    """
    if "session_id" not in st.session_state:
        # ランダムな文字列（セッションID）を、ログ出力用に作成
        st.session_state.session_id = uuid4().hex


def initialize_retriever():
    """
    画面読み込み時にRAGのRetriever（ベクターストアから検索するオブジェクト）を作成
    """
    # ロガーを読み込むことで、後続の処理中に発生したエラーなどがログファイルに記録される
    logger = logging.getLogger(ct.LOGGER_NAME)

    # すでにRetrieverが作成済みの場合、後続の処理を中断
    if "retriever" in st.session_state:
        return
    
    try:
        # RAGの参照先となるデータソースの読み込み
        logger.info("データソースの読み込み開始")
        docs_all = load_data_sources()
        logger.info(f"データソース読み込み完了: {len(docs_all)}件")

        # OSがWindowsの場合、Unicode正規化と、cp932（Windows用の文字コード）で表現できない文字を除去
        for doc in docs_all:
            doc.page_content = adjust_string(doc.page_content)
            for key in doc.metadata:
                doc.metadata[key] = adjust_string(doc.metadata[key])
        
        # OpenAI API Key の確認
        import os
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY環境変数が設定されていません")
        logger.info("OPENAI_API_KEY環境変数が設定されています")
        
        # 埋め込みモデルの用意
        logger.info("OpenAIEmbeddingsの初期化開始")
        embeddings = OpenAIEmbeddings()
        logger.info("OpenAIEmbeddingsの初期化完了")
        
        # チャンク分割用のオブジェクトを作成
        # チュンク変数を変数化
        text_splitter = CharacterTextSplitter(
            chunk_size=ct.CHUNK_SIZE_NUMBER,
            chunk_overlap=ct.CHUNK_OVERLAP_NUMBER,
            separator="\n"
        )

        # チャンク分割を実施
        logger.info("チャンク分割開始")
        splitted_docs = text_splitter.split_documents(docs_all)
        logger.info(f"チャンク分割完了: {len(splitted_docs)}件")

        # ベクターストアの作成
        logger.info("ベクターストア作成開始")
        db = Chroma.from_documents(splitted_docs, embedding=embeddings)
        logger.info("ベクターストア作成完了")

        # ベクターストアを検索するRetrieverの作成
        #st.session_state.retriever = db.as_retriever(search_kwargs={"k": 3})
        st.session_state.retriever = db.as_retriever(search_kwargs={"k": 7})
        logger.info("Retriever作成完了")
        
    except Exception as e:
        logger.error(f"initialize_retrieverでエラーが発生しました: {type(e).__name__}: {str(e)}")
        raise


def initialize_session_state():
    """
    初期化データの用意
    """
    if "messages" not in st.session_state:
        # 「表示用」の会話ログを順次格納するリストを用意
        st.session_state.messages = []
        # 「LLMとのやりとり用」の会話ログを順次格納するリストを用意
        st.session_state.chat_history = []


def load_data_sources():
    """
    RAGの参照先となるデータソースの読み込み

    Returns:
        読み込んだ通常データソース
    """
    # データソースを格納する用のリスト
    docs_all = []
    # ファイル読み込みの実行（渡した各リストにデータが格納される）
    recursive_file_check(ct.RAG_TOP_FOLDER_PATH, docs_all)

    web_docs_all = []
    # ファイルとは別に、指定のWebページ内のデータも読み込み
    # 読み込み対象のWebページ一覧に対して処理
    for web_url in ct.WEB_URL_LOAD_TARGETS:
        # 指定のWebページを読み込み
        loader = WebBaseLoader(web_url)
        web_docs = loader.load()
        # for文の外のリストに読み込んだデータソースを追加
        web_docs_all.extend(web_docs)
    # 通常読み込みのデータソースにWebページのデータを追加
    docs_all.extend(web_docs_all)

    return docs_all


def recursive_file_check(path, docs_all):
    """
    RAGの参照先となるデータソースの読み込み

    Args:
        path: 読み込み対象のファイル/フォルダのパス
        docs_all: データソースを格納する用のリスト
    """
    # パスがフォルダかどうかを確認
    if os.path.isdir(path):
        # フォルダの場合、フォルダ内のファイル/フォルダ名の一覧を取得
        files = os.listdir(path)
        # 各ファイル/フォルダに対して処理
        for file in files:
            # ファイル/フォルダ名だけでなく、フルパスを取得
            full_path = os.path.join(path, file)
            # フルパスを渡し、再帰的にファイル読み込みの関数を実行
            recursive_file_check(full_path, docs_all)
    else:
        # パスがファイルの場合、ファイル読み込み
        file_load(path, docs_all)


def file_load(path, docs_all):
    """
    ファイル内のデータ読み込み

    Args:
        path: ファイルパス
        docs_all: データソースを格納する用のリスト
    """
    # ファイルの拡張子を取得
    file_extension = os.path.splitext(path)[1]
    # ファイル名（拡張子を含む）を取得
    file_name = os.path.basename(path)

    # 想定していたファイル形式の場合のみ読み込む
    if file_extension in ct.SUPPORTED_EXTENSIONS:
        # ファイルの拡張子に合ったdata loaderを使ってデータ読み込み
        loader = ct.SUPPORTED_EXTENSIONS[file_extension](path)
        docs = loader.load()
        
        # 各ドキュメントのメタデータを拡張
        for doc in docs:
            # 既存のメタデータを保持しつつ、追加情報を格納
            doc.metadata.update({
                'file_name': file_name,
                'file_path': path,
                'file_extension': file_extension,
                'content_preview': doc.page_content[:100] + "..." if len(doc.page_content) > 100 else doc.page_content,
                'content_length': len(doc.page_content)
            })
            
            # PDFファイルの場合、ページ番号情報をより詳細に処理
            if file_extension == ".pdf" and 'page' in doc.metadata:
                # ページ番号を1ベースに調整（PyMuPDFLoaderは0ベース）
                doc.metadata['page'] = doc.metadata.get('page', 0) + 1
                doc.metadata['page_info'] = f"ページ {doc.metadata['page']}"
            
            # DOCXファイルの場合、ページ情報を推定
            elif file_extension == ".docx":
                # 文字数からページ数を推定（1ページあたり約400文字と仮定）
                estimated_page = (len(doc.page_content) // 400) + 1
                doc.metadata['estimated_page'] = estimated_page
                doc.metadata['page_info'] = f"推定ページ {estimated_page}"
            
            # CSVファイルの場合、行番号情報を追加
            elif file_extension == ".csv":
                if 'row' in doc.metadata:
                    doc.metadata['row_info'] = f"行 {doc.metadata['row']}"
        
        # CSVファイルの統合方法をより詳細に制御
        if file_extension == ".csv" and docs:
            # ヘッダー行を取得（最初の行）
            header_row = docs[0].page_content if docs else ""
            
            # データ行を結合（ヘッダーを除く）
            data_rows = [doc.page_content for doc in docs[1:]] if len(docs) > 1 else []
            
            # 表形式で整理した内容を作成
            combined_content = f"【CSVデータ】\nヘッダー: {header_row}\n\nデータ行:\n" + "\n".join(data_rows)
            
            # メタデータにヘッダー情報も追加
            combined_doc = type(docs[0])(
                page_content=combined_content,
                metadata={
                    'source': path,
                    'file_name': file_name,
                    'file_path': path,
                    'file_extension': file_extension,
                    'content_preview': combined_content[:100] + "..." if len(combined_content) > 100 else combined_content,
                    'content_length': len(combined_content),
                    'total_rows': len(docs),
                    'document_type': 'csv_unified',
                    'csv_header': header_row,
                    'data_rows_count': len(data_rows)
                }
            )
            # 統合されたドキュメントのみを追加
            docs_all.append(combined_doc)
        else:
            # CSV以外のファイルは従来通り
            docs_all.extend(docs)


def adjust_string(s):
    """
    Windows環境でRAGが正常動作するよう調整
    
    Args:
        s: 調整を行う文字列
    
    Returns:
        調整を行った文字列
    """
    # 調整対象は文字列のみ
    if type(s) is not str:
        return s

    # OSがWindowsの場合、Unicode正規化と、cp932（Windows用の文字コード）で表現できない文字を除去
    if sys.platform.startswith("win"):
        s = unicodedata.normalize('NFC', s)
        s = s.encode("cp932", "ignore").decode("cp932")
        return s
    
    # OSがWindows以外の場合はそのまま返す
    return s