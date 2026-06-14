enum StyleTemplate {
  hongguoInspired('hongguo_inspired'),
  douyinInspired('douyin_inspired'),
  hippoInspired('hippo_inspired'),
  reelshortInspired('reelshort_inspired');

  const StyleTemplate(this.wireValue);

  final String wireValue;
}

enum StoreComplianceMode {
  appStore('app_store'),
  playStore('play_store'),
  androidDirect('android_direct'),
  regionalUserChoice('regional_user_choice');

  const StoreComplianceMode(this.wireValue);

  final String wireValue;
}

enum AuthProvider {
  email('email'),
  google('google'),
  facebook('facebook'),
  apple('apple');

  const AuthProvider(this.wireValue);

  final String wireValue;
}

enum ConsumerPaymentProvider {
  iap('iap'),
  playBilling('play_billing'),
  stripe('stripe'),
  paypal('paypal'),
  bankTransfer('bank_transfer'),
  localWallet('local_wallet'),
  crypto('crypto'),
  pointCard('point_card');

  const ConsumerPaymentProvider(this.wireValue);

  final String wireValue;
}

class AppCapabilities {
  const AppCapabilities({
    required this.styleTemplate,
    required this.storeComplianceMode,
    required this.authProviders,
    required this.consumerPaymentProviders,
  });

  const AppCapabilities.defaults()
      : styleTemplate = StyleTemplate.hongguoInspired,
        storeComplianceMode = StoreComplianceMode.appStore,
        authProviders = const {AuthProvider.email, AuthProvider.apple},
        consumerPaymentProviders = const {ConsumerPaymentProvider.iap};

  final StyleTemplate styleTemplate;
  final StoreComplianceMode storeComplianceMode;
  final Set<AuthProvider> authProviders;
  final Set<ConsumerPaymentProvider> consumerPaymentProviders;

  List<AuthProvider> get normalizedAuthProviders {
    final normalized = <AuthProvider>{...authProviders};
    final needsApple = storeComplianceMode == StoreComplianceMode.appStore &&
        (normalized.contains(AuthProvider.google) ||
            normalized.contains(AuthProvider.facebook));
    if (needsApple) {
      normalized.add(AuthProvider.apple);
    }
    return AuthProvider.values.where(normalized.contains).toList();
  }

  bool get externalPaymentsAllowed {
    return storeComplianceMode == StoreComplianceMode.androidDirect ||
        storeComplianceMode == StoreComplianceMode.regionalUserChoice;
  }

  List<ConsumerPaymentProvider> get visiblePaymentProviders {
    return visiblePaymentProvidersFromWire(
      consumerPaymentProviders.map((provider) => provider.wireValue),
    );
  }

  AppCapabilities constrainedByNativeBuild(AppCapabilities nativeBuild) {
    return AppCapabilities(
      styleTemplate: styleTemplate,
      storeComplianceMode: nativeBuild.storeComplianceMode,
      authProviders: authProviders,
      consumerPaymentProviders: nativeBuild
          .visiblePaymentProvidersFromWire(
            consumerPaymentProviders.map((provider) => provider.wireValue),
          )
          .toSet(),
    );
  }

  List<ConsumerPaymentProvider> visiblePaymentProvidersFromWire(
    Iterable<String> providerWireValues,
  ) {
    final requested = providerWireValues.toSet();
    final allowed = switch (storeComplianceMode) {
      StoreComplianceMode.appStore => const {ConsumerPaymentProvider.iap},
      StoreComplianceMode.playStore => const {
          ConsumerPaymentProvider.playBilling,
        },
      StoreComplianceMode.regionalUserChoice => const {
          ConsumerPaymentProvider.playBilling,
          ConsumerPaymentProvider.stripe,
          ConsumerPaymentProvider.paypal,
          ConsumerPaymentProvider.bankTransfer,
          ConsumerPaymentProvider.localWallet,
          ConsumerPaymentProvider.pointCard,
        },
      StoreComplianceMode.androidDirect => const {
          ConsumerPaymentProvider.stripe,
          ConsumerPaymentProvider.paypal,
          ConsumerPaymentProvider.bankTransfer,
          ConsumerPaymentProvider.localWallet,
          ConsumerPaymentProvider.crypto,
          ConsumerPaymentProvider.pointCard,
        },
    };
    return ConsumerPaymentProvider.values
        .where(
          (provider) =>
              allowed.contains(provider) &&
              requested.contains(provider.wireValue),
        )
        .toList();
  }

  Map<String, Object> toPublicJson() {
    return {
      'styleTemplate': styleTemplate.wireValue,
      'storeComplianceMode': storeComplianceMode.wireValue,
      'authProviders': normalizedAuthProviders
          .map((provider) => provider.wireValue)
          .toList(),
      'consumerPaymentProviders': visiblePaymentProviders
          .map((provider) => provider.wireValue)
          .toList(),
      'externalPaymentsAllowed': externalPaymentsAllowed,
    };
  }
}
