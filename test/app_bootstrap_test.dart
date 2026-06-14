import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:short_drama_whitelabel/app/short_drama_app.dart';
import 'package:short_drama_whitelabel/core/api/tenant_adapter_client.dart';
import 'package:short_drama_whitelabel/flavor/flavor.dart';

class FakeAdapterTransport implements AdapterTransport {
  FakeAdapterTransport(this.responses);

  final List<AdapterResponse> responses;
  final List<AdapterRequest> requests = [];

  @override
  Future<AdapterResponse> send(AdapterRequest request) async {
    requests.add(request);
    if (responses.isEmpty) {
      throw StateError('No fake response configured for ${request.path}.');
    }
    return responses.removeAt(0);
  }
}

AdapterResponse ok(Map<String, dynamic> body) {
  return AdapterResponse(statusCode: 200, body: jsonEncode(body));
}

AdapterResponse unavailable(String path) {
  return AdapterResponse(
    statusCode: 503,
    body: jsonEncode({
      'error': {
        'code': 'TENANT_EDGE_UNAVAILABLE',
        'message': '$path is unavailable',
        'requestId': 'req_unavailable',
      },
    }),
  );
}

Map<String, dynamic> configPayload() {
  return {
    'requestId': 'req_config',
    'status': 'ok',
    'config': {
      'tenant': {
        'id': 'tenant_1001',
        'appKey': 'pk_tenant_1001',
        'name': 'Remote Drama',
        'brandName': 'Remote Drama',
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
        'externalPaymentsAllowed': true,
        'consumerLedgerScope': 'consumer',
      },
      'theme': {
        'primaryColor': '#5B21B6',
        'logoUrl': '/logo.png',
        'posterAspectRatio': '2:3',
      },
      'legal': {
        'customerServiceUrl': '/support',
        'termsUrl': '/terms',
        'privacyUrl': '/privacy',
      },
      'endpoints': {
        'config': '/config',
        'catalog': '/catalog',
        'dramaDetail': '/dramas/{dramaId}',
        'play': '/play',
        'me': '/me',
        'wallet': '/wallet',
        'paymentOptions': '/payment/options',
      },
    },
  };
}

void main() {
  testWidgets('remote config overrides template while native build caps payments',
      (tester) async {
    final payload = configPayload();
    final config = payload['config'] as Map<String, dynamic>;
    final tenant = config['tenant'] as Map<String, dynamic>;
    final app = config['app'] as Map<String, dynamic>;
    final theme = config['theme'] as Map<String, dynamic>;
    tenant['name'] = 'Tenant Picked Drama';
    tenant['brandName'] = 'Tenant Picked Drama';
    app['styleTemplate'] = 'reelshort_inspired';
    app['storeComplianceMode'] = 'android_direct';
    app['consumerPaymentProviders'] = ['stripe', 'crypto', 'point_card'];
    theme['primaryColor'] = '#E11D48';

    final transport = FakeAdapterTransport([
      ok(payload),
      ok({
        'requestId': 'req_catalog',
        'status': 'ok',
        'items': [
          {
            'dramaId': 'drama_remote',
            'title': 'Remote Cliffhanger',
            'posterUrl': '/posters/remote.png',
            'episodeCount': 18,
            'readyEpisodeCount': 7,
            'pointPrice': 3,
          },
        ],
      }),
      ok({
        'requestId': 'req_me',
        'status': 'ok',
        'account': {
          'tenantId': 'tenant_1001',
          'accountRefMasked': 'anon:r...1234',
          'authProviders': ['email', 'google'],
          'membershipTier': 'guest',
          'deletionEndpoint': '/me/delete-request',
        },
      }),
      ok({
        'requestId': 'req_wallet',
        'status': 'ok',
        'wallet': {
          'tenantId': 'tenant_1001',
          'accountRefMasked': 'anon:r...1234',
          'ledgerScope': 'consumer',
          'balanceCoins': 88,
          'membershipTier': 'guest',
          'currency': 'coins',
        },
      }),
      ok({
        'requestId': 'req_wallet_ledger',
        'status': 'ok',
        'ledgerScope': 'consumer',
        'accountRefMasked': 'anon:r...1234',
        'entries': const [],
      }),
      ok({
        'requestId': 'req_payment_options',
        'status': 'ok',
        'providers': ['stripe', 'crypto', 'point_card'],
        'externalPaymentsAllowed': true,
        'ledgerScope': 'consumer',
        'storeComplianceMode': 'android_direct',
      }),
    ]);

    await tester.pumpWidget(
      ShortDramaApp(
        flavor: FlavorConfig.hongguo(),
        client: TenantAdapterClient(
          baseUri: Uri.parse('https://tenant-edge.example.test'),
          transport: transport,
        ),
        endUserRef: 'anon:goldfruit-install-widget',
        loadRemoteConfig: true,
      ),
    );

    await tester.pumpAndSettle();

    expect(find.text('Tenant Picked Drama'), findsOneWidget);
    expect(find.text('Every episode ends on a cliff'), findsOneWidget);
    expect(find.text('Cliffhanger Premium'), findsWidgets);
    expect(find.text('app store'), findsOneWidget);
    expect(find.text('payments gated'), findsOneWidget);
    expect(find.text('android direct'), findsNothing);
    expect(find.text('3 payment methods'), findsNothing);
    expect(find.text('Free-to-start drama theater'), findsNothing);
  });

  testWidgets('remote bootstrap renders tenant catalog and wallet state', (
    tester,
  ) async {
    final transport = FakeAdapterTransport([
      ok(configPayload()),
      ok({
        'requestId': 'req_catalog',
        'status': 'ok',
        'items': [
          {
            'dramaId': 'drama_remote',
            'title': 'Remote Hit',
            'posterUrl': '/posters/remote.png',
            'episodeCount': 24,
            'readyEpisodeCount': 6,
            'pointPrice': 2,
          },
        ],
      }),
      ok({
        'requestId': 'req_me',
        'status': 'ok',
        'account': {
          'tenantId': 'tenant_1001',
          'accountRefMasked': 'anon:r...1234',
          'authProviders': ['email', 'google'],
          'membershipTier': 'guest',
          'deletionEndpoint': '/me/delete-request',
        },
      }),
      ok({
        'requestId': 'req_wallet',
        'status': 'ok',
        'wallet': {
          'tenantId': 'tenant_1001',
          'accountRefMasked': 'anon:r...1234',
          'ledgerScope': 'consumer',
          'balanceCoins': 88,
          'membershipTier': 'guest',
          'currency': 'coins',
        },
      }),
      ok({
        'requestId': 'req_wallet_ledger',
        'status': 'ok',
        'ledgerScope': 'consumer',
        'accountRefMasked': 'anon:r...1234',
        'entries': [
          {
            'ledgerId': 'ledger_bootstrap_1',
            'type': 'payment',
            'title': 'Starter recharge',
            'pointsDelta': 88,
            'balanceAfter': 88,
            'createdAt': '2026-06-14T00:00:00Z',
            'status': 'posted',
          },
        ],
      }),
      ok({
        'requestId': 'req_payment_options',
        'status': 'ok',
        'providers': ['stripe', 'point_card'],
        'externalPaymentsAllowed': true,
        'ledgerScope': 'consumer',
        'storeComplianceMode': 'android_direct',
      }),
    ]);
    final client = TenantAdapterClient(
      baseUri: Uri.parse('https://tenant-edge.example.test'),
      transport: transport,
    );

    await tester.pumpWidget(
      ShortDramaApp(
        flavor: FlavorConfig.douyin(),
        client: client,
        endUserRef: 'anon:pulsedrama-install-widget',
        loadRemoteConfig: true,
      ),
    );
    expect(find.text('Loading tenant app'), findsOneWidget);

    await tester.pumpAndSettle();

    expect(find.text('Remote Hit'), findsWidgets);
    final navigation = tester.widget<NavigationBar>(
      find.byType(NavigationBar),
    );
    expect(
      navigation.indicatorColor,
      const Color(0xFF5B21B6).withValues(alpha: 0.18),
    );
    await tester.tap(find.text('Mine'));
    await tester.pumpAndSettle();
    expect(find.textContaining('anon:r...1234'), findsOneWidget);
    await tester.tap(find.text('Wallet Center'));
    await tester.pumpAndSettle();
    expect(find.text('88 coins'), findsOneWidget);
    await tester.scrollUntilVisible(find.text('Starter recharge'), 300);
    expect(find.text('Starter recharge'), findsOneWidget);
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
        'anon:pulsedrama-install-widget',
        'anon:pulsedrama-install-widget',
        'anon:pulsedrama-install-widget',
      ],
    );
  });

  testWidgets('tenant edge failure keeps the app usable with local demo data', (
    tester,
  ) async {
    final transport = FakeAdapterTransport([unavailable('/config')]);
    final client = TenantAdapterClient(
      baseUri: Uri.parse('https://tenant-edge.example.test'),
      transport: transport,
    );

    await tester.pumpWidget(
      ShortDramaApp(
        flavor: FlavorConfig.hongguo(),
        client: client,
        endUserRef: 'anon:goldfruit-install-widget',
        loadRemoteConfig: true,
      ),
    );

    await tester.pumpAndSettle();

    expect(find.text('Seed Drama'), findsWidgets);
    expect(
      find.text('Tenant Edge offline, showing local template data.'),
      findsOneWidget,
    );
    expect(find.text('Tenant Edge unavailable'), findsNothing);
    expect(transport.requests.map((request) => request.path), ['/config']);
  });
}
