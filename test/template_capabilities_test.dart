import 'package:flutter_test/flutter_test.dart';
import 'package:short_drama_whitelabel/core/config/app_capabilities.dart';
import 'package:short_drama_whitelabel/flavor/flavor.dart';

void main() {
  test('app store compliance only exposes store-safe payment providers', () {
    const capabilities = AppCapabilities(
      styleTemplate: StyleTemplate.hongguoInspired,
      storeComplianceMode: StoreComplianceMode.appStore,
      authProviders: {
        AuthProvider.email,
        AuthProvider.google,
        AuthProvider.facebook,
      },
      consumerPaymentProviders: {
        ConsumerPaymentProvider.iap,
        ConsumerPaymentProvider.stripe,
        ConsumerPaymentProvider.paypal,
        ConsumerPaymentProvider.bankTransfer,
        ConsumerPaymentProvider.localWallet,
        ConsumerPaymentProvider.crypto,
        ConsumerPaymentProvider.pointCard,
      },
    );

    expect(capabilities.normalizedAuthProviders, contains(AuthProvider.apple));
    expect(capabilities.visiblePaymentProviders, [ConsumerPaymentProvider.iap]);
    expect(capabilities.externalPaymentsAllowed, isFalse);
  });

  test(
    'remote payment options are filtered by local store compliance mode',
    () {
      const capabilities = AppCapabilities(
        styleTemplate: StyleTemplate.hongguoInspired,
        storeComplianceMode: StoreComplianceMode.appStore,
        authProviders: {AuthProvider.email, AuthProvider.apple},
        consumerPaymentProviders: {
          ConsumerPaymentProvider.iap,
          ConsumerPaymentProvider.stripe,
          ConsumerPaymentProvider.paypal,
        },
      );

      expect(
        capabilities.visiblePaymentProvidersFromWire([
          'iap',
          'stripe',
          'paypal',
        ]),
        [ConsumerPaymentProvider.iap],
      );
    },
  );

  test('android direct compliance exposes tenant-owned external payments', () {
    const capabilities = AppCapabilities(
      styleTemplate: StyleTemplate.reelshortInspired,
      storeComplianceMode: StoreComplianceMode.androidDirect,
      authProviders: {AuthProvider.email, AuthProvider.google},
      consumerPaymentProviders: {
        ConsumerPaymentProvider.stripe,
        ConsumerPaymentProvider.paypal,
        ConsumerPaymentProvider.bankTransfer,
        ConsumerPaymentProvider.localWallet,
        ConsumerPaymentProvider.crypto,
        ConsumerPaymentProvider.pointCard,
      },
    );

    expect(
      capabilities.normalizedAuthProviders,
      isNot(contains(AuthProvider.apple)),
    );
    expect(
      capabilities.visiblePaymentProviders,
      containsAll([
        ConsumerPaymentProvider.stripe,
        ConsumerPaymentProvider.paypal,
        ConsumerPaymentProvider.bankTransfer,
        ConsumerPaymentProvider.localWallet,
        ConsumerPaymentProvider.crypto,
        ConsumerPaymentProvider.pointCard,
      ]),
    );
    expect(capabilities.externalPaymentsAllowed, isTrue);
  });

  test('MVP flavors map to distinct style templates with CoolShow first', () {
    final templates = [
      FlavorConfig.coolshow().capabilities.styleTemplate,
      FlavorConfig.hongguo().capabilities.styleTemplate,
      FlavorConfig.douyin().capabilities.styleTemplate,
      FlavorConfig.hippo().capabilities.styleTemplate,
      FlavorConfig.reelshort().capabilities.styleTemplate,
    ];

    expect(templates.toSet(), {
      StyleTemplate.coolshow,
      StyleTemplate.hongguoInspired,
      StyleTemplate.douyinInspired,
      StyleTemplate.hippoInspired,
      StyleTemplate.reelshortInspired,
    });
  });

  test('publishable flavor config never exposes server secret fields', () {
    final payload = FlavorConfig.coolshow().toPublicTemplateConfig();
    final serialized = payload.toString().toLowerCase();

    expect(payload['styleTemplate'], 'coolshow');
    expect(payload['storeComplianceMode'], 'android_direct');
    expect(payload['consumerPaymentProviders'], contains('point_card'));
    expect(serialized, isNot(contains('secret')));
    expect(serialized, isNot(contains('sk_')));
    expect(serialized, isNot(contains('tenant_app_secret')));
  });
}
