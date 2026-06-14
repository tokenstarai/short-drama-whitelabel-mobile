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
          'tokenExpiresAt': '2026-06-14T00:00:00Z',
        },
      }),
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
    expect(find.textContaining('Episode 2'), findsOneWidget);
    expect(find.text('Authorized player'), findsNothing);

    await tester.tap(find.text('Unlock and Play'));
    await tester.pumpAndSettle();

    expect(transport.requests, hasLength(2));
    expect(transport.requests.last.body?['episodeId'], 'episode_2');
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
