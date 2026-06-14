import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:short_drama_whitelabel/app/app_runtime.dart';
import 'package:short_drama_whitelabel/core/api/tenant_adapter_client.dart';
import 'package:short_drama_whitelabel/core/config/app_capabilities.dart';
import 'package:short_drama_whitelabel/flavor/flavor.dart';

class RuntimeFakeTransport implements AdapterTransport {
  RuntimeFakeTransport(this.responses);

  final List<AdapterResponse> responses;
  final List<AdapterRequest> requests = [];

  @override
  Future<AdapterResponse> send(AdapterRequest request) async {
    requests.add(request);
    return responses.removeAt(0);
  }
}

AdapterResponse runtimeOk(Map<String, dynamic> body) {
  return AdapterResponse(statusCode: 200, body: jsonEncode(body));
}

void main() {
  test(
    'bootstrap loads public config and catalog while keeping fallback usable',
    () async {
      final transport = RuntimeFakeTransport([
        runtimeOk({
          'requestId': 'req_config',
          'status': 'ok',
          'config': {
            'tenant': {
              'id': 'tenant_1001',
              'appKey': 'pk_tenant_1001',
              'name': 'Pulse Drama',
              'brandName': 'DramaHub',
              'defaultLocale': 'en-US',
              'supportedLocales': ['en-US', 'zh-CN'],
            },
            'features': {
              'enableCardRedeem': true,
              'enableOfflineTopup': true,
              'enableOnlinePayment': true,
              'enableAdsUnlock': true,
              'enableAccountDeletion': true,
            },
            'app': {
              'styleTemplate': 'douyin_inspired',
              'storeComplianceMode': 'android_direct',
              'authProviders': ['email', 'google'],
              'consumerPaymentProviders': ['stripe', 'point_card'],
            },
            'legal': {
              'customerServiceUrl': '/support',
              'termsUrl': '/terms',
              'privacyUrl': '/privacy',
            },
          },
        }),
        runtimeOk({
          'requestId': 'req_catalog',
          'status': 'ok',
          'items': [
            {
              'dramaId': 'drama_1',
              'title': 'Runtime Drama',
              'posterUrl': '/posters/1.png',
              'episodeCount': 8,
              'readyEpisodeCount': 3,
              'pointPrice': 2,
            },
          ],
        }),
        runtimeOk({
          'requestId': 'req_me',
          'status': 'ok',
          'account': {
            'tenantId': 'tenant_1001',
            'accountRefMasked': 'anon:f...vice',
            'authProviders': ['email', 'google'],
            'membershipTier': 'guest',
            'deletionEndpoint': '/me/delete-request',
          },
        }),
        runtimeOk({
          'requestId': 'req_wallet',
          'status': 'ok',
          'wallet': {
            'tenantId': 'tenant_1001',
            'accountRefMasked': 'anon:f...vice',
            'ledgerScope': 'consumer',
            'balanceCoins': 88,
            'membershipTier': 'guest',
            'currency': 'coins',
          },
        }),
        runtimeOk({
          'requestId': 'req_wallet_ledger',
          'status': 'ok',
          'ledgerScope': 'consumer',
          'accountRefMasked': 'anon:f...vice',
          'entries': [
            {
              'ledgerId': 'ledger_runtime_1',
              'type': 'point_card',
              'title': 'Point card recharge',
              'pointsDelta': 88,
              'balanceAfter': 88,
              'createdAt': '2026-06-14T00:00:00Z',
              'status': 'posted',
            },
          ],
        }),
        runtimeOk({
          'requestId': 'req_options',
          'status': 'ok',
          'providers': ['stripe', 'point_card'],
          'externalPaymentsAllowed': true,
          'ledgerScope': 'consumer',
          'storeComplianceMode': 'android_direct',
        }),
      ]);
      final runtime = AppRuntime(
        flavor: FlavorConfig.hongguo(),
        endUserRef: 'anon:goldfruit-install-runtime',
        client: TenantAdapterClient(
          baseUri: Uri.parse('https://tenant-edge.example.test'),
          transport: transport,
        ),
      );

      await runtime.bootstrap();

      expect(runtime.loading, isFalse);
      expect(runtime.appName, 'Pulse Drama');
      expect(runtime.catalog.single.title, 'Runtime Drama');
      expect(runtime.account?.accountRefMasked, 'anon:f...vice');
      expect(runtime.wallet?.balanceCoins, 88);
      expect(runtime.walletLedger?.entries.single.pointsDelta, 88);
      expect(runtime.paymentOptions?.providers, ['stripe', 'point_card']);
      expect(
        runtime.effectiveCapabilities.styleTemplate.wireValue,
        'douyin_inspired',
      );
      expect(transport.requests.map((request) => request.path), [
        '/config',
        '/catalog',
        '/me',
        '/wallet',
        '/wallet/ledger',
        '/payment/options',
      ]);
      expect(
        transport.requests
            .where(
              (request) =>
                  request.path == '/me' ||
                  request.path == '/wallet' ||
                  request.path == '/wallet/ledger',
            )
            .map((request) => request.headers['x-device-id']),
        [
          'anon:goldfruit-install-runtime',
          'anon:goldfruit-install-runtime',
          'anon:goldfruit-install-runtime',
        ],
      );
    },
  );

  test('wallet ledger failure keeps wallet and payment options usable',
      () async {
    final transport = RuntimeFakeTransport([
      runtimeOk({
        'requestId': 'req_config',
        'status': 'ok',
        'config': {
          'tenant': {
            'id': 'tenant_1001',
            'appKey': 'pk_tenant_1001',
            'name': 'Pulse Drama',
            'brandName': 'DramaHub',
            'defaultLocale': 'en-US',
            'supportedLocales': ['en-US', 'zh-CN'],
          },
          'features': {
            'enableCardRedeem': true,
            'enableOfflineTopup': true,
            'enableOnlinePayment': true,
            'enableAdsUnlock': true,
            'enableAccountDeletion': true,
          },
          'app': {
            'styleTemplate': 'douyin_inspired',
            'storeComplianceMode': 'android_direct',
            'authProviders': ['email', 'google'],
            'consumerPaymentProviders': ['stripe', 'point_card'],
          },
          'legal': {
            'customerServiceUrl': '/support',
            'termsUrl': '/terms',
            'privacyUrl': '/privacy',
          },
        },
      }),
      runtimeOk({
        'requestId': 'req_catalog',
        'status': 'ok',
        'items': [
          {
            'dramaId': 'drama_1',
            'title': 'Runtime Drama',
            'posterUrl': '/posters/1.png',
            'episodeCount': 8,
            'readyEpisodeCount': 3,
            'pointPrice': 2,
          },
        ],
      }),
      runtimeOk({
        'requestId': 'req_me',
        'status': 'ok',
        'account': {
          'tenantId': 'tenant_1001',
          'accountRefMasked': 'anon:f...vice',
          'authProviders': ['email', 'google'],
          'membershipTier': 'guest',
          'deletionEndpoint': '/me/delete-request',
        },
      }),
      runtimeOk({
        'requestId': 'req_wallet',
        'status': 'ok',
        'wallet': {
          'tenantId': 'tenant_1001',
          'accountRefMasked': 'anon:f...vice',
          'ledgerScope': 'consumer',
          'balanceCoins': 88,
          'membershipTier': 'guest',
          'currency': 'coins',
        },
      }),
      const AdapterResponse(
        statusCode: 503,
        body:
            '{"error":{"code":"LEDGER_DOWN","message":"ledger down","requestId":"req_ledger_down"}}',
      ),
      runtimeOk({
        'requestId': 'req_options',
        'status': 'ok',
        'providers': ['stripe', 'point_card'],
        'externalPaymentsAllowed': true,
        'ledgerScope': 'consumer',
        'storeComplianceMode': 'android_direct',
      }),
    ]);
    final runtime = AppRuntime(
      flavor: FlavorConfig.hongguo(),
      endUserRef: 'anon:goldfruit-install-ledger',
      client: TenantAdapterClient(
        baseUri: Uri.parse('https://tenant-edge.example.test'),
        transport: transport,
      ),
    );

    await runtime.bootstrap();

    expect(runtime.wallet?.balanceCoins, 88);
    expect(runtime.walletLedger?.entries, isEmpty);
    expect(runtime.paymentOptions?.providers, ['stripe', 'point_card']);
    expect(transport.requests.map((request) => request.path), [
      '/config',
      '/catalog',
      '/me',
      '/wallet',
      '/wallet/ledger',
      '/payment/options',
    ]);
    expect(
      transport.requests
          .where(
            (request) =>
                request.path == '/me' ||
                request.path == '/wallet' ||
                request.path == '/wallet/ledger',
          )
          .map((request) => request.headers['x-device-id']),
      [
        'anon:goldfruit-install-ledger',
        'anon:goldfruit-install-ledger',
        'anon:goldfruit-install-ledger',
      ],
    );
  });

  test(
    'bootstrap keeps sample catalog when Tenant Edge is unavailable',
    () async {
      final transport = RuntimeFakeTransport([
        const AdapterResponse(
          statusCode: 503,
          body:
              '{"error":{"code":"DOWN","message":"down","requestId":"req_down"}}',
        ),
      ]);
      final runtime = AppRuntime(
        flavor: FlavorConfig.reelshort(),
        client: TenantAdapterClient(
          baseUri: Uri.parse('https://tenant-edge.example.test'),
          transport: transport,
        ),
      );

      await runtime.bootstrap();

      expect(runtime.loading, isFalse);
      expect(runtime.error, isNotNull);
      expect(runtime.catalog, isNotEmpty);
      expect(runtime.appName, 'Cliff Drama');
    },
  );

  test('remote config default locale drives runtime strings', () async {
    final transport = RuntimeFakeTransport([
      runtimeOk({
        'requestId': 'req_config',
        'status': 'ok',
        'config': {
          'tenant': {
            'id': 'tenant_1001',
            'appKey': 'pk_tenant_1001',
            'name': 'Pulse Drama',
            'brandName': 'DramaHub',
            'defaultLocale': 'zh-CN',
            'supportedLocales': ['zh-CN', 'en-US'],
          },
          'features': {
            'enableCardRedeem': true,
            'enableOfflineTopup': true,
            'enableOnlinePayment': true,
            'enableAdsUnlock': true,
            'enableAccountDeletion': true,
          },
          'app': {
            'styleTemplate': 'douyin_inspired',
            'storeComplianceMode': 'android_direct',
            'authProviders': ['email', 'google'],
            'consumerPaymentProviders': ['stripe', 'point_card'],
          },
          'legal': {
            'customerServiceUrl': '/support',
            'termsUrl': '/terms',
            'privacyUrl': '/privacy',
          },
        },
      }),
      runtimeOk({
        'requestId': 'req_catalog',
        'status': 'ok',
        'items': const [],
      }),
      runtimeOk({
        'requestId': 'req_me',
        'status': 'ok',
        'account': {
          'tenantId': 'tenant_1001',
          'accountRefMasked': 'anon:f...vice',
          'authProviders': ['email', 'google'],
          'membershipTier': 'guest',
          'deletionEndpoint': '/me/delete-request',
        },
      }),
      runtimeOk({
        'requestId': 'req_wallet',
        'status': 'ok',
        'wallet': {
          'tenantId': 'tenant_1001',
          'accountRefMasked': 'anon:f...vice',
          'ledgerScope': 'consumer',
          'balanceCoins': 0,
          'membershipTier': 'guest',
          'currency': 'coins',
        },
      }),
      runtimeOk({
        'requestId': 'req_wallet_ledger',
        'status': 'ok',
        'ledgerScope': 'consumer',
        'accountRefMasked': 'anon:f...vice',
        'entries': const [],
      }),
      runtimeOk({
        'requestId': 'req_options',
        'status': 'ok',
        'providers': ['stripe', 'point_card'],
        'externalPaymentsAllowed': true,
        'ledgerScope': 'consumer',
        'storeComplianceMode': 'android_direct',
      }),
    ]);
    final runtime = AppRuntime(
      flavor: FlavorConfig.reelshort(),
      localeCode: 'fil-PH',
      client: TenantAdapterClient(
        baseUri: Uri.parse('https://tenant-edge.example.test'),
        transport: transport,
      ),
    );

    await runtime.bootstrap();

    expect(runtime.localeCode, 'zh-CN');
    expect(runtime.supportedLocaleCodes, ['zh-CN', 'en-US']);
    expect(runtime.strings.home, '首页');

    runtime.setLocale('en-US');
    expect(runtime.localeCode, 'en-US');
    expect(runtime.strings.home, 'Home');

    runtime.setLocale('vi-VN');
    expect(runtime.localeCode, 'en-US');
  });

  test(
    'native store build caps remote compliance mode and payment providers',
    () async {
      final transport = RuntimeFakeTransport([
        runtimeOk({
          'requestId': 'req_config',
          'status': 'ok',
          'config': {
            'tenant': {
              'id': 'tenant_1001',
              'appKey': 'pk_tenant_1001',
              'name': 'Remote Direct Drama',
              'brandName': 'Remote Direct Drama',
              'defaultLocale': 'en-US',
              'supportedLocales': ['en-US', 'zh-CN'],
            },
            'features': {
              'enableCardRedeem': true,
              'enableOfflineTopup': true,
              'enableOnlinePayment': true,
              'enableAdsUnlock': true,
              'enableAccountDeletion': true,
            },
            'app': {
              'styleTemplate': 'douyin_inspired',
              'storeComplianceMode': 'android_direct',
              'authProviders': ['email', 'google', 'facebook'],
              'consumerPaymentProviders': [
                'iap',
                'stripe',
                'crypto',
                'point_card',
              ],
            },
            'legal': {
              'customerServiceUrl': '/support',
              'termsUrl': '/terms',
              'privacyUrl': '/privacy',
            },
          },
        }),
        runtimeOk({
          'requestId': 'req_catalog',
          'status': 'ok',
          'items': const [],
        }),
        runtimeOk({
          'requestId': 'req_me',
          'status': 'ok',
          'account': {
            'tenantId': 'tenant_1001',
            'accountRefMasked': 'anon:s...tore',
            'authProviders': ['email', 'google', 'facebook'],
            'membershipTier': 'guest',
            'deletionEndpoint': '/me/delete-request',
          },
        }),
        runtimeOk({
          'requestId': 'req_wallet',
          'status': 'ok',
          'wallet': {
            'tenantId': 'tenant_1001',
            'accountRefMasked': 'anon:s...tore',
            'ledgerScope': 'consumer',
            'balanceCoins': 0,
            'membershipTier': 'guest',
            'currency': 'coins',
          },
        }),
        runtimeOk({
          'requestId': 'req_wallet_ledger',
          'status': 'ok',
          'ledgerScope': 'consumer',
          'accountRefMasked': 'anon:s...tore',
          'entries': const [],
        }),
        runtimeOk({
          'requestId': 'req_options',
          'status': 'ok',
          'providers': ['iap', 'stripe', 'crypto', 'point_card'],
          'externalPaymentsAllowed': true,
          'ledgerScope': 'consumer',
          'storeComplianceMode': 'android_direct',
        }),
      ]);
      final runtime = AppRuntime(
        flavor: FlavorConfig.hongguo(),
        endUserRef: 'anon:goldfruit-native-store-cap',
        client: TenantAdapterClient(
          baseUri: Uri.parse('https://tenant-edge.example.test'),
          transport: transport,
        ),
      );

      await runtime.bootstrap();

      expect(runtime.effectiveCapabilities.styleTemplate.wireValue,
          'douyin_inspired');
      expect(
        runtime.effectiveCapabilities.storeComplianceMode,
        StoreComplianceMode.appStore,
      );
      expect(
        runtime.effectiveCapabilities.normalizedAuthProviders,
        contains(AuthProvider.apple),
      );
      expect(runtime.effectivePaymentProviderWireValues, ['iap']);
    },
  );
}
