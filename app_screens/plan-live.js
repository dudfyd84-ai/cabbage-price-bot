// 프리미엄 구독 플랜 연동 및 사용자 요금제(Tier) 설정
(function () {
  const FREE_TIER = 'free';
  const STANDARD_TIER = 'standard';

  // 로컬 스토리지에서 현재 사용자 티어 로드 (기본값: free)
  let currentTier = localStorage.getItem('ct_user_tier') || FREE_TIER;
  if (!localStorage.getItem('ct_user_tier')) {
    localStorage.setItem('ct_user_tier', FREE_TIER);
  }

  const btnFree = document.getElementById('btn-plan-free');
  const btnStandard = document.getElementById('btn-plan-standard');

  const updateUI = () => {
    if (!btnFree || !btnStandard) return;

    if (currentTier === STANDARD_TIER) {
      // 1) Standard 플랜 이용 중인 상태
      btnFree.textContent = '무료 요금제로 변경 (다운그레이드)';
      btnFree.className = 'mt-xl w-full py-md border border-primary text-primary font-label-md text-label-md rounded-lg hover:bg-surface-container-low transition-colors cursor-pointer';
      btnFree.disabled = false;

      btnStandard.textContent = '현재 이용 중 (Standard)';
      btnStandard.className = 'mt-xl w-full py-md bg-primary-container text-white font-label-md text-label-md rounded-lg border border-primary-fixed-dim cursor-default opacity-80';
      btnStandard.disabled = true;
    } else {
      // 2) Free 플랜 이용 중인 상태
      btnFree.textContent = '현재 이용 중';
      btnFree.className = 'mt-xl w-full py-md border border-outline text-outline font-label-md text-label-md rounded-lg bg-surface-container-low cursor-default';
      btnFree.disabled = true;

      btnStandard.textContent = '업그레이드 하기';
      btnStandard.className = 'mt-xl w-full py-md bg-white text-primary font-label-md text-label-md rounded-lg hover:bg-secondary-fixed transition-colors font-bold cursor-pointer';
      btnStandard.disabled = false;
    }
  };

  // 버튼 이벤트 리스너 추가
  if (btnFree) {
    btnFree.addEventListener('click', () => {
      if (currentTier === STANDARD_TIER) {
        if (confirm('무료 요금제로 다운그레이드 하시겠습니까?\n일부 30일 예측 정보 및 무제한 BOM 기능이 제한될 수 있습니다.')) {
          currentTier = FREE_TIER;
          localStorage.setItem('ct_user_tier', FREE_TIER);
          alert('무료 요금제로 변경되었습니다.');
          updateUI();
          location.reload();
        }
      }
    });
  }

  if (btnStandard) {
    btnStandard.addEventListener('click', () => {
      if (currentTier === FREE_TIER) {
        if (confirm('Standard 플랜으로 업그레이드 하시겠습니까?\n(매월 30일 예측 분석 및 안전 재고 알림 기능이 무제한 제공됩니다)')) {
          currentTier = STANDARD_TIER;
          localStorage.setItem('ct_user_tier', STANDARD_TIER);
          alert('Standard 요금제로 업그레이드 되었습니다!\n프리미엄 기능이 활성화됩니다.');
          updateUI();
          location.reload();
        }
      }
    });
  }

  // 초기 렌더링 실행
  updateUI();
})();
