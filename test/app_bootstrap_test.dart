import 'dart:convert';
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:short_drama_whitelabel/app/short_drama_app.dart';
import 'package:short_drama_whitelabel/core/api/tenant_adapter_client.dart';
import 'package:short_drama_whitelabel/features/player/player_screen.dart';
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

class TestAppDeepLinks implements AppDeepLinks {
  TestAppDeepLinks({Uri? initialLink})
      : _initialLink = Future.value(initialLink);

  final Future<Uri?> _initialLink;
  final controller = StreamController<Uri>.broadcast();

  @override
  Future<Uri?> getInitialLink() => _initialLink;

  @override
  Stream<Uri> get uriLinkStream => controller.stream;

  Future<void> dispose() => controller.close();
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
  testWidgets(
      'share deep link opens its player episode without network request',
      (tester) async {
    final links = TestAppDeepLinks(
      initialLink: Uri.parse(
        'goldfruitdrama://dramas/drama_2/episodes/drama_2_ep_003',
      ),
    );
    addTearDown(links.dispose);
    final transport = FakeAdapterTransport([]);

    await tester.pumpWidget(
      ShortDramaApp(
        flavor: FlavorConfig.hongguo(),
        client: TenantAdapterClient(
          baseUri: Uri.parse('https://tenant-edge.example.test'),
          transport: transport,
        ),
        endUserRef: 'anon:goldfruit-share-deeplink-widget',
        deepLinks: links,
      ),
    );

    await tester.pumpAndSettle();

    expect(find.textContaining('Heiress Returns'), findsWidgets);
    expect(find.textContaining('Episode 3'), findsWidgets);
    expect(find.text('Unlock and Play'), findsOneWidget);
    expect(transport.requests, isEmpty);
  });

  testWidgets('share deep link fetches public detail when catalog lacks drama',
      (tester) async {
    final links = TestAppDeepLinks(
      initialLink: Uri.parse(
        'goldfruitdrama://dramas/drama_remote_share/episodes/episode_remote_2',
      ),
    );
    addTearDown(links.dispose);
    final transport = FakeAdapterTransport([
      ok({
        'requestId': 'req_shared_detail',
        'status': 'ok',
        'drama': {
          'dramaId': 'drama_remote_share',
          'title': 'Shared Public Drama',
          'posterUrl': '/posters/shared.png',
          'episodeCount': 2,
          'readyEpisodeCount': 2,
          'pointPrice': 3,
          'episodes': [
            {
              'episodeId': 'episode_remote_1',
              'episodeNumber': 1,
              'title': 'Shared Episode 1',
              'pointPrice': 3,
              'ready': true,
              'locked': false,
            },
            {
              'episodeId': 'episode_remote_2',
              'episodeNumber': 2,
              'title': 'Shared Episode 2',
              'pointPrice': 3,
              'ready': true,
              'locked': true,
            },
          ],
        },
      }),
    ]);

    await tester.pumpWidget(
      ShortDramaApp(
        flavor: FlavorConfig.hongguo(),
        client: TenantAdapterClient(
          baseUri: Uri.parse('https://tenant-edge.example.test'),
          transport: transport,
        ),
        endUserRef: 'anon:goldfruit-remote-share-widget',
        deepLinks: links,
      ),
    );

    await tester.pumpAndSettle();

    expect(find.textContaining('Shared Public Drama'), findsWidgets);
    expect(find.textContaining('Shared Episode 2'), findsWidgets);
    expect(find.text('Unlock and Play'), findsOneWidget);
    expect(transport.requests.single.path, '/dramas/drama_remote_share');
  });

  testWidgets('share deep link ignores duplicate initial and stream uri',
      (tester) async {
    final uri = Uri.parse(
      'goldfruitdrama://dramas/drama_duplicate_share/episodes/episode_duplicate_1',
    );
    final links = TestAppDeepLinks(initialLink: uri);
    addTearDown(links.dispose);
    final transport = FakeAdapterTransport([
      ok({
        'requestId': 'req_duplicate_detail',
        'status': 'ok',
        'drama': {
          'dramaId': 'drama_duplicate_share',
          'title': 'Duplicate Shared Drama',
          'posterUrl': '/posters/duplicate.png',
          'episodeCount': 1,
          'readyEpisodeCount': 1,
          'pointPrice': 2,
          'episodes': [
            {
              'episodeId': 'episode_duplicate_1',
              'episodeNumber': 1,
              'title': 'Duplicate Episode 1',
              'pointPrice': 2,
              'ready': true,
              'locked': false,
            },
          ],
        },
      }),
    ]);

    await tester.pumpWidget(
      ShortDramaApp(
        flavor: FlavorConfig.hongguo(),
        client: TenantAdapterClient(
          baseUri: Uri.parse('https://tenant-edge.example.test'),
          transport: transport,
        ),
        endUserRef: 'anon:goldfruit-duplicate-share-widget',
        deepLinks: links,
      ),
    );
    await tester.pumpAndSettle();

    links.controller.add(uri);
    await tester.pumpAndSettle();

    expect(find.textContaining('Duplicate Shared Drama'), findsWidgets);
    expect(find.textContaining('Duplicate Episode 1'), findsWidgets);
    expect(
      find.byType(PlayerScreen, skipOffstage: false),
      findsOneWidget,
    );
    expect(transport.requests.single.path, '/dramas/drama_duplicate_share');
  });

  testWidgets(
      'remote config overrides template while native build caps payments',
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
    await tester.scrollUntilVisible(
      find.text('app store'),
      240,
      scrollable: find.byType(Scrollable).first,
    );
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

    expect(find.text('Contract Wife'), findsWidgets);
    expect(
      find.text('Tenant Edge offline, showing local template data.'),
      findsOneWidget,
    );
    expect(find.text('Tenant Edge unavailable'), findsNothing);
    expect(transport.requests.map((request) => request.path), ['/config']);
  });
}
