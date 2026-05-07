# ─── 세션 상태 초기화 (Phase 관리 추가) ───
for key, default in [
    ("draft_text", None), 
    ("combined_critique", None), 
    ("track_a_text", None), 
    ("track_b_text", None),
    ("phase", 0), # 0: 대기, 1: 경쟁 완료, 2: 최종 발행
    ("winning_track", None),
    ("tuned_results", {}), ("seo_data", None), ("selected_topic", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ─── 글쓰기 시작 버튼 ───
if st.session_state.phase == 0:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        can_write = len(selected_models) > 0
        if not can_write:
            st.info("💡 문체 튜닝할 AI 모델을 1개 이상 선택해 주세요.")
        
        if st.button("✍️ 1단계: 다중 에이전트 경쟁 모드 시작", use_container_width=True, disabled=not can_write):
            st.session_state.selected_topic = selected
            topic_only = selected.split(" → ")[-1] if " → " in selected else selected
            
            # 0단계: 공공 API 데이터 수집
            with st.spinner("🏢 정부 공공 API 데이터를 수집하고 있습니다..."):
                gov_data_text, gov_count = collect_gov_data(topic_only)
            
            # 2단계: DeepSeek 초안
            with st.spinner("📝 DeepSeek V4가 공통 기술 초안을 작성하고 있습니다..."):
                try:
                    draft = generate_draft(topic_only, combined_text, gov_data_text)
                    st.session_state.draft_text = draft
                except Exception as e:
                    st.error(f"초안 작성 중 오류: {e}")
                    st.stop()
            
            # 3단계: 다중 관점 비판 (Gemini + Llama)
            with st.spinner("🔍 Gemini 1.5 Pro(논리)와 Llama 3 70B(가독성)가 초안을 비판하고 있습니다..."):
                try:
                    critique_g = critique_with_gemini(draft, topic_only)
                except Exception as e:
                    critique_g = f"[Gemini 비판 실패] {e}"
                    
                try:
                    from pipeline import critique_with_llama
                    critique_l = critique_with_llama(draft, topic_only)
                except Exception as e:
                    critique_l = f"[Llama 비판 실패] {e}"
                    
                st.session_state.combined_critique = f"【논리/팩트 비판 (Gemini 1.5 Pro)】\n{critique_g}\n\n---\n\n【가독성/문체 비판 (Llama 3 70B)】\n{critique_l}"
            
            # 4단계: 트랙 A & B 병렬 수정
            critique_text = st.session_state.combined_critique
            
            with st.spinner("🤖 트랙 A: DeepSeek V4가 통합 비판을 수용하여 초안을 수정합니다..."):
                try:
                    st.session_state.track_a_text = revise_draft(draft, critique_text, topic_only)
                except Exception as e:
                    st.session_state.track_a_text = f"[트랙 A 오류] {e}"
                    
            with st.spinner("🦙 트랙 B: Llama 3 70B가 통합 비판을 수용하여 초안을 수정합니다..."):
                try:
                    from pipeline import revise_with_llama
                    st.session_state.track_b_text = revise_with_llama(draft, critique_text, topic_only)
                except Exception as e:
                    st.session_state.track_b_text = f"[트랙 B 오류] {e}"
            
            st.session_state.phase = 1
            st.rerun()

# ═══════════════════════════════════════════
#  Phase 1: 경쟁 모드 대시보드
# ═══════════════════════════════════════════
if st.session_state.phase == 1:
    topic = st.session_state.selected_topic
    st.markdown('<hr class="divider">', unsafe_allow_html=True)
    st.markdown("### ⚔️ [Phase 1] 다중 에이전트 수정본 경쟁")
    st.markdown("통합 비판문을 바탕으로 작성된 두 가지 수정본을 비교하고, 최종 발행할 버전을 선택해 주세요.")
    
    with st.expander("🔍 통합 비판문 확인 (Gemini + Llama 3)", expanded=False):
        st.markdown(st.session_state.combined_critique)
        
    col_a, col_b = st.columns(2)
    
    with col_a:
        st.markdown("#### 🤖 트랙 A (DeepSeek V4)")
        st.info("논리적 무결점과 구조화에 강점이 있습니다.")
        with st.expander("트랙 A 수정본 읽기", expanded=True):
            st.markdown(st.session_state.track_a_text)
            
    with col_b:
        st.markdown("#### 🦙 트랙 B (Llama 3 70B)")
        st.success("유려한 문체와 뛰어난 가독성에 강점이 있습니다.")
        with st.expander("트랙 B 수정본 읽기", expanded=True):
            st.markdown(st.session_state.track_b_text)
            
    st.markdown("<br/>", unsafe_allow_html=True)
    st.markdown("### 🏆 최종 우승 트랙 선택")
    
    winner = st.radio("어떤 수정본이 더 마음에 드시나요?", ["트랙 A (DeepSeek V4)", "트랙 B (Llama 3 70B)"], horizontal=True)
    
    col_btn1, col_btn2, col_btn3 = st.columns([1, 2, 1])
    with col_btn2:
        if st.button("✅ 선택한 트랙으로 2단계(문체 튜닝/발행) 진행", use_container_width=True):
            st.session_state.winning_track = "A" if "A" in winner else "B"
            winning_text = st.session_state.track_a_text if st.session_state.winning_track == "A" else st.session_state.track_b_text
            topic_only = topic.split(" → ")[-1] if " → " in topic else topic
            
            # 문체 튜닝
            tuned = {}
            for m_name in selected_models:
                with st.spinner(f"🎨 {TUNING_MODELS[m_name]['icon']} {m_name}가 최종 문체를 다듬고 있습니다..."):
                    try:
                        tuned[m_name] = tune_with_model(winning_text, topic_only, m_name)
                    except Exception as e:
                        tuned[m_name] = f"[오류] {m_name} 튜닝 실패: {e}"
            st.session_state.tuned_results = tuned
            
            # SEO
            with st.spinner("🔍 SEO 메타데이터를 생성하고 있습니다..."):
                try:
                    seo = generate_seo_metadata(topic_only, winning_text)
                    st.session_state.seo_data = seo
                except Exception:
                    st.session_state.seo_data = None
                    
            st.session_state.phase = 2
            st.rerun()

# ═══════════════════════════════════════════
#  Phase 2: 퍼블리싱 대시보드
# ═══════════════════════════════════════════
if st.session_state.phase == 2:
    topic = st.session_state.selected_topic
    topic_short = topic.split(" → ")[-1] if " → " in topic else topic
    tuned = st.session_state.tuned_results
    seo = st.session_state.seo_data
    winning_text = st.session_state.track_a_text if st.session_state.winning_track == "A" else st.session_state.track_b_text
    
    st.markdown('<hr class="divider">', unsafe_allow_html=True)
    st.markdown(f"### 🚀 [Phase 2] 최종 퍼블리싱 (승자: 트랙 {st.session_state.winning_track})")
    
    # 5단계: 문체 튜닝
    if tuned:
        for m_name, m_text in tuned.items():
            info = TUNING_MODELS.get(m_name, {})
            icon = info.get("icon", "🎨")
            with st.expander(f"{icon} 문체 튜닝 최종본 ({m_name})", expanded=True):
                st.markdown(m_text)
    
    # SEO & 이미지 가이드
    with st.expander("🔍 SEO 메타데이터 & 이미지 가이드", expanded=False):
        if seo:
            st.markdown("**검색 최적화 태그 (네이버/구글)**")
            tag_html = " ".join([f'<span class="model-badge" style="background:#667eea;margin:2px;">#{t}</span>' for t in seo.get("seo_tags", [])])
            st.markdown(tag_html, unsafe_allow_html=True)
            st.markdown("")
            st.markdown("**메타 설명문 (150자)**")
            st.info(seo.get("meta_description", ""))
            st.markdown("**이미지 대체 텍스트 (Alt Text) 추천**")
            for i, alt in enumerate(seo.get("image_alt_texts", []), 1):
                st.markdown(f"{i}. {alt}")
        else:
            st.caption("SEO 데이터 생성에 실패했습니다.")
            
    # ─── 내보내기 ───
    st.markdown('<hr class="divider">', unsafe_allow_html=True)
    col_d1, col_d2, col_d3 = st.columns(3)
    
    with col_d1:
        # Create DOCX requires critique text. Since we combined it, we use it here.
        docx_bytes = create_docx(
            topic_short, st.session_state.draft_text, st.session_state.combined_critique, winning_text, tuned, seo
        )
        st.download_button(
            label="📥 워드(.docx) 다운로드",
            data=docx_bytes,
            file_name=f"프로젝트소민_{topic_short[:20]}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            use_container_width=True,
        )
    
    with col_d2:
        # 티스토리 자동 발행 버튼
        best_text = list(tuned.values())[0] if tuned else winning_text
        seo_tags = seo.get("seo_tags", []) if seo else []
        html_content = f"<h2>{topic_short}</h2>\n\n{best_text}"
        
        blog_name = os.getenv("TISTORY_BLOG_NAME", "")
        chrome_dir = os.getenv("CHROME_USER_DATA_DIR", "")
        can_publish = bool(blog_name and chrome_dir)
        
        if not can_publish:
            st.warning("⚠️ .env에 TISTORY_BLOG_NAME과\nCHROME_USER_DATA_DIR를 설정하세요")
        
        if st.button("🚀 티스토리로 즉시 발행(딸깍)", use_container_width=True, disabled=not can_publish):
            status_placeholder = st.empty()
            progress_bar = st.progress(0)
            steps = ["브라우저 준비", "글쓰기 이동", "제목 입력", "HTML 입력", "태그 입력", "발행 클릭"]
            step_idx = [0]
            
            def update_status(msg):
                status_placeholder.info(msg)
                if step_idx[0] < len(steps):
                    progress_bar.progress((step_idx[0] + 1) / len(steps))
                    step_idx[0] += 1
            
            publisher = TistoryPublisher(headless=False, status_callback=update_status)
            result = publisher.publish(
                title=topic_short,
                html_content=html_content,
                tags=seo_tags,
            )
            
            progress_bar.progress(1.0)
            if result["success"]:
                st.success(result["message"])
                if result["url"]:
                    st.markdown(f"[🔗 발행된 글 보기]({result['url']})")
            else:
                st.error(result["message"])
    
    with col_d3:
        # HTML 미리보기
        with st.expander("💻 HTML 미리보기", expanded=False):
            seo_tags_str = ", ".join(seo.get("seo_tags", [])) if seo else ""
            preview_html = f"<h2>{topic_short}</h2>\n\n{best_text}"
            if seo_tags_str:
                preview_html += f"\n\n<p><b>태그:</b> {seo_tags_str}</p>"
            st.code(preview_html, language="html")
            st.caption("↑ 수동 복사용 HTML")

# ─── 새로 분석하기 버튼 ───
st.markdown("")
col_a, col_b, col_c = st.columns([1, 2, 1])
with col_b:
    if st.button("🔄 새로운 주제 분석하기", use_container_width=True):
        for k in ["draft_text", "combined_critique", "track_a_text", "track_b_text", "tuned_results", "seo_data", "selected_topic", "winning_track"]:
            st.session_state[k] = None if k != "tuned_results" else {}
        st.session_state.phase = 0
        st.rerun()
