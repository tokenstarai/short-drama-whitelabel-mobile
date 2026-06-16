import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:short_drama_whitelabel/app/app_runtime.dart';
import 'package:short_drama_whitelabel/core/api/app_models.dart';
import 'package:short_drama_whitelabel/core/api/tenant_adapter_client.dart';
import 'package:short_drama_whitelabel/features/account/account_screen.dart';
import 'package:short_drama_whitelabel/features/player/player_screen.dart';
import 'package:short_drama_whitelabel/flavor/flavor.dart';

class PlayerFakeTransport implements AdapterTransport {
  final List<AdapterRequest> requests = [];

  @override
  Future<AdapterResponse> send(AdapterRequest request) async {
    requests.add(request);
    return AdapterResponse(
      statusCode: 200,
      body: jsonEncode({
        'requestId': 'req_play_widget',
        'status': 'authorized',
        'grantId': 'grant_${request.body?['episodeId']}',
        'charge': {'points': 2, 'balanceAfter': 6},
        'playback': {
          'playerUrl': 'https://player.example/widget',
          'manifestHost': 'stream.example',
          'tokenExpiresAt': '2099-01-01T00:00:00.000Z',
        },
      }),
    );
  }
}

class PlayerErrorTransport implements AdapterTransport {
  PlayerErrorTransport({required this.code, required this.message});

  final String code;
  final String message;
  final List<AdapterRequest> requests = [];

  @override
  Future<AdapterResponse> send(AdapterRequest request) async {
    requests.add(request);
    return AdapterResponse(
      statusCode: 409,
      body: jsonEncode({
        'error': {
          'code': code,
          'message': message,
          'requestId': 'req_player_error',
        },
      }),
    );
  }
}

class PlayerSequenceTransport implements AdapterTransport {
  PlayerSequenceTransport(this.responses);

  final List<Map<String, dynamic>> responses;
  final List<AdapterRequest> requests = [];

  @override
  Future<AdapterResponse> send(AdapterRequest request) async {
    requests.add(request);
    final index = requests.length - 1;
    return AdapterResponse(
      statusCode: 200,
      body: jsonEncode(responses[index.clamp(0, responses.length - 1)]),
    );
  }
}

void main() {
  testWidgets('player uses runtime end-user reference for play requests', (
    tester,
  ) async {
    final transport = PlayerFakeTransport();
    final flavor = FlavorConfig.hongguo();
    final runtime = AppRuntime(
      flavor: flavor,
      endUserRef: 'anon:goldfruit-install-player',
      client: TenantAdapterClient(
        baseUri: Uri.parse('https://tenant-edge.example.test'),
        transport: transport,
      ),
    );
    addTearDown(runtime.dispose);

    await tester.pumpWidget(
      AppRuntimeScope(
        runtime: runtime,
        child: MaterialApp(
          home: PlayerScreen(
            flavor: flavor,
            dramaId: 'drama_1',
            episodeId: 'episode_1',
            enableNativeVideo: false,
          ),
        ),
      ),
    );

    await tester.tap(find.text('Unlock and Play'));
    await tester.pumpAndSettle();

    expect(transport.requests.single.path, '/play');
    expect(
      transport.requests.single.body?['endUserRef'],
      'anon:goldfruit-install-player',
    );
  });

  testWidgets('player switches ready episodes and resets authorization', (
    tester,
  ) async {
    final transport = PlayerFakeTransport();
    final flavor = FlavorConfig.hongguo();
    final runtime = AppRuntime(
      flavor: flavor,
      endUserRef: 'anon:goldfruit-install-player',
      client: TenantAdapterClient(
        baseUri: Uri.parse('https://tenant-edge.example.test'),
        transport: transport,
      ),
    );
    addTearDown(runtime.dispose);

    await tester.pumpWidget(
      AppRuntimeScope(
        runtime: runtime,
        child: MaterialApp(
          home: PlayerScreen(
            flavor: flavor,
            dramaId: 'drama_1',
            episodeId: 'episode_1',
            episodeTitle: 'Episode 1',
            enableNativeVideo: false,
            episodes: const [
              DramaEpisode(
                episodeId: 'episode_1',
                episodeNumber: 1,
                title: 'Episode 1',
                pointPrice: 2,
                ready: true,
                locked: false,
              ),
              DramaEpisode(
                episodeId: 'episode_2',
                episodeNumber: 2,
                title: 'Episode 2',
                pointPrice: 2,
                ready: true,
                locked: true,
              ),
            ],
          ),
        ),
      ),
    );

    await tester.tap(find.text('Unlock and Play'));
    await tester.pumpAndSettle();
    expect(find.text('Authorized player'), findsOneWidget);
    expect(transport.requests.single.body?['episodeId'], 'episode_1');

    await tester.tap(find.text('Next'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Episode 2'), findsWidgets);
    expect(find.text('Authorized player'), findsNothing);

    await tester.tap(find.text('Unlock and Play'));
    await tester.pumpAndSettle();

    expect(transport.requests, hasLength(2));
    expect(transport.requests.last.body?['episodeId'], 'episode_2');
  });

  testWidgets('player episode list sheet switches ready episodes', (
    tester,
  ) async {
    final transport = PlayerFakeTransport();
    final flavor = FlavorConfig.hongguo();
    final runtime = AppRuntime(
      flavor: flavor,
      endUserRef: 'anon:goldfruit-install-player',
      client: TenantAdapterClient(
        baseUri: Uri.parse('https://tenant-edge.example.test'),
        transport: transport,
      ),
    );
    addTearDown(runtime.dispose);

    await tester.pumpWidget(
      AppRuntimeScope(
        runtime: runtime,
        child: MaterialApp(
          home: PlayerScreen(
            flavor: flavor,
            dramaId: 'drama_1',
            episodeId: 'episode_1',
            episodeTitle: 'Episode 1',
            enableNativeVideo: false,
            episodes: const [
              DramaEpisode(
                episodeId: 'episode_1',
                episodeNumber: 1,
                title: 'Episode 1',
                pointPrice: 2,
                ready: true,
                locked: false,
              ),
              DramaEpisode(
                episodeId: 'episode_2',
                episodeNumber: 2,
                title: 'Episode 2',
                pointPrice: 4,
                ready: true,
                locked: true,
              ),
              DramaEpisode(
                episodeId: 'episode_3',
                episodeNumber: 3,
                title: 'Episode 3',
                pointPrice: 4,
                ready: false,
                locked: true,
              ),
            ],
          ),
        ),
      ),
    );

    await tester.tap(find.text('Unlock and Play'));
    await tester.pumpAndSettle();
    expect(find.text('Authorized player'), findsOneWidget);

    await tester.tap(find.byIcon(Icons.list_alt));
    await tester.pumpAndSettle();
    expect(find.text('Episode List'), findsOneWidget);
    expect(find.text('Episode 1'), findsWidgets);
    expect(find.text('Episode 2'), findsWidgets);
    expect(find.text('Episode 3'), findsNothing);

    await tester.tap(find.text('Episode 2').last);
    await tester.pumpAndSettle();

    expect(find.textContaining('Episode 2'), findsWidgets);
    expect(find.text('Authorized player'), findsNothing);
    expect(transport.requests, hasLength(1));
  });

  testWidgets('player share action opens tenant-safe share sheet', (
    tester,
  ) async {
    final transport = PlayerFakeTransport();
    final flavor = FlavorConfig.hongguo();
    final runtime = AppRuntime(
      flavor: flavor,
      endUserRef: 'anon:goldfruit-install-player',
      client: TenantAdapterClient(
        baseUri: Uri.parse('https://tenant-edge.example.test'),
        transport: transport,
      ),
    );
    addTearDown(runtime.dispose);

    await tester.pumpWidget(
      AppRuntimeScope(
        runtime: runtime,
        child: MaterialApp(
          home: PlayerScreen(
            flavor: flavor,
            dramaId: 'drama_share',
            episodeId: 'episode_share_1',
            dramaTitle: 'Share Runtime Drama',
            episodeTitle: 'Share Episode 1',
            enableNativeVideo: false,
          ),
        ),
      ),
    );

    await tester.tap(find.byIcon(Icons.share_outlined));
    await tester.pumpAndSettle();

    expect(find.text('Share Drama'), findsOneWidget);
    expect(find.text('Share Runtime Drama'), findsWidgets);
    expect(find.text('Share Episode 1'), findsOneWidget);
    expect(find.text('Copy Link'), findsOneWidget);
    expect(
      find.textContaining(
        'goldfruitdrama://dramas/drama_share/episodes/episode_share_1',
      ),
      findsOneWidget,
    );
    expect(transport.requests, isEmpty);
  });

  testWidgets('player maps playback authorization errors to friendly text', (
    tester,
  ) async {
    final cases = <({String code, String friendly})>[
      (
        code: 'APP_INSUFFICIENT_BALANCE',
        friendly:
            'This content is temporarily unavailable. Please try again later.',
      ),
      (
        code: 'APP_EPISODE_NOT_READY',
        friendly: 'This episode is being prepared.'
      ),
      (code: 'APP_NOT_FOUND', friendly: 'This content is not available yet.'),
      (
        code: 'APP_PLAYBACK_TOKEN_FAILED',
        friendly: 'Playback authorization failed. Please retry.',
      ),
    ];

    for (final testCase in cases) {
      final transport = PlayerErrorTransport(
        code: testCase.code,
        message: 'upstream detail ${testCase.code}',
      );
      final flavor = FlavorConfig.hongguo();
      final runtime = AppRuntime(
        flavor: flavor,
        endUserRef: 'anon:goldfruit-player-error',
        client: TenantAdapterClient(
          baseUri: Uri.parse('https://tenant-edge.example.test'),
          transport: transport,
        ),
      );
      addTearDown(runtime.dispose);

      await tester.pumpWidget(
        AppRuntimeScope(
          runtime: runtime,
          child: MaterialApp(
            home: PlayerScreen(
              flavor: flavor,
              dramaId: 'drama_error',
              episodeId: 'episode_error',
              enableNativeVideo: false,
            ),
          ),
        ),
      );

      await tester.tap(find.text('Unlock and Play'));
      await tester.pumpAndSettle();

      expect(find.text(testCase.friendly), findsOneWidget);
      expect(find.textContaining(testCase.code), findsNothing);
      expect(find.textContaining('req_player_error'), findsNothing);
    }
  });

  testWidgets('player silently refreshes expired playback token', (
    tester,
  ) async {
    final transport = PlayerSequenceTransport([
      {
        'requestId': 'req_play_expired',
        'status': 'authorized',
        'grantId': 'grant_refresh',
        'charge': {'points': 2, 'balanceAfter': 6},
        'playback': {
          'playerUrl': 'https://player.example/expired',
          'manifestHost': 'stream.example',
          'tokenExpiresAt': '2020-01-01T00:00:00.000Z',
        },
      },
      {
        'requestId': 'req_play_refreshed',
        'status': 'authorized',
        'grantId': 'grant_refresh',
        'charge': {'points': 2, 'balanceAfter': 6},
        'playback': {
          'playerUrl': 'https://player.example/fresh',
          'manifestHost': 'stream.example',
          'tokenExpiresAt': '2099-01-01T00:00:00.000Z',
        },
      },
    ]);
    final flavor = FlavorConfig.hongguo();
    final runtime = AppRuntime(
      flavor: flavor,
      endUserRef: 'anon:goldfruit-player-refresh',
      client: TenantAdapterClient(
        baseUri: Uri.parse('https://tenant-edge.example.test'),
        transport: transport,
      ),
    );
    addTearDown(runtime.dispose);

    await tester.pumpWidget(
      AppRuntimeScope(
        runtime: runtime,
        child: MaterialApp(
          home: PlayerScreen(
            flavor: flavor,
            dramaId: 'drama_refresh',
            episodeId: 'episode_refresh',
            enableNativeVideo: false,
          ),
        ),
      ),
    );

    await tester.tap(find.text('Unlock and Play'));
    await tester.pumpAndSettle();

    expect(transport.requests, hasLength(2));
    expect(
      transport.requests.first.headers['idempotency-key'],
      transport.requests.last.headers['idempotency-key'],
    );
    expect(find.textContaining('Grant grant_refresh'), findsOneWidget);
    expect(find.textContaining('https://player.example/fresh'), findsOneWidget);
    expect(find.textContaining('https://player.example/expired'), findsNothing);
    expect(find.text('Playback authorization failed. Please retry.'),
        findsNothing);
  });

  testWidgets('authorized playback appears in account watch history', (
    tester,
  ) async {
    final transport = PlayerFakeTransport();
    final flavor = FlavorConfig.hongguo();
    final runtime = AppRuntime(
      flavor: flavor,
      endUserRef: 'anon:goldfruit-install-player',
      client: TenantAdapterClient(
        baseUri: Uri.parse('https://tenant-edge.example.test'),
        transport: transport,
      ),
    );
    addTearDown(runtime.dispose);

    await tester.pumpWidget(
      AppRuntimeScope(
        runtime: runtime,
        child: MaterialApp(
          home: PlayerScreen(
            flavor: flavor,
            dramaId: 'drama_1',
            episodeId: 'episode_1',
            dramaTitle: 'Runtime Drama',
            episodeTitle: 'Pilot Hook',
            enableNativeVideo: false,
          ),
        ),
      ),
    );

    await tester.tap(find.text('Unlock and Play'));
    await tester.pumpAndSettle();

    await tester.pumpWidget(
      AppRuntimeScope(
        runtime: runtime,
        child: MaterialApp(home: AccountScreen(flavor: flavor)),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Watch History'));
    await tester.pumpAndSettle();

    expect(find.text('Runtime Drama'), findsOneWidget);
    expect(find.text('Pilot Hook'), findsOneWidget);
  });

  testWidgets('favorite toggle is reflected in account favorites', (
    tester,
  ) async {
    final transport = PlayerFakeTransport();
    final flavor = FlavorConfig.hongguo();
    final runtime = AppRuntime(
      flavor: flavor,
      endUserRef: 'anon:goldfruit-install-player',
      client: TenantAdapterClient(
        baseUri: Uri.parse('https://tenant-edge.example.test'),
        transport: transport,
      ),
    );
    addTearDown(runtime.dispose);

    await tester.pumpWidget(
      AppRuntimeScope(
        runtime: runtime,
        child: MaterialApp(
          home: PlayerScreen(
            flavor: flavor,
            dramaId: 'drama_1',
            episodeId: 'episode_1',
            dramaTitle: 'Runtime Drama',
            episodeTitle: 'Pilot Hook',
            enableNativeVideo: false,
          ),
        ),
      ),
    );

    await tester.tap(find.byIcon(Icons.favorite_border));
    await tester.pumpAndSettle();

    expect(find.byIcon(Icons.favorite), findsOneWidget);

    await tester.pumpWidget(
      AppRuntimeScope(
        runtime: runtime,
        child: MaterialApp(home: AccountScreen(flavor: flavor)),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Favorites'));
    await tester.pumpAndSettle();

    expect(find.text('Runtime Drama'), findsOneWidget);
  });
}
