class FeatureFlags {
  const FeatureFlags({
    required this.enableCardRedeem,
    required this.enableOfflineTopup,
    required this.enableOnlinePayment,
    required this.enableAdsUnlock,
    required this.enableAccountDeletion,
  });

  const FeatureFlags.defaults()
      : enableCardRedeem = false,
        enableOfflineTopup = false,
        enableOnlinePayment = false,
        enableAdsUnlock = true,
        enableAccountDeletion = true;

  final bool enableCardRedeem;
  final bool enableOfflineTopup;
  final bool enableOnlinePayment;
  final bool enableAdsUnlock;
  final bool enableAccountDeletion;

  List<String> visibleWalletEntrypoints() {
    return [
      if (enableCardRedeem) 'cardRedeem',
      if (enableOfflineTopup) 'offlineTopup',
      if (enableOnlinePayment) 'onlinePayment',
    ];
  }
}
