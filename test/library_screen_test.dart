import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'dart:convert';

import 'package:short_drama_whitelabel/app/app_runtime.dart';
import 'package:short_drama_whitelabel/core/api/tenant_adapter_client.dart';
import 'package:short_drama_whitelabel/features/account/account_screen.dart';
import 'package:short_drama_whitelabel/flavor/flavor.dart';

class LibraryFakeTransport implements AdapterTransport {
  final List<AdapterRequest> requests = [];

  @override
  Future<AdapterResponse> send(AdapterRequest request) async {
    requests.add(request);
    if (request.path == '/dramas/drama_favorite') {
      return AdapterResponse(
        statusCode: 200,
        body: jsonEncode({
          'requestId': 'req_library_favorite_detail',
          'drama': {
            'dramaId': 'drama_favorite',
            'title': 'Favorite Runtime Drama',
            'summary': 'Public favorite detail',
            'posterUrl': 'https://cdn.example/favorite.jpg',
            'episodeCount': 2,
            'readyEpisodeCount': 2,
            'pointPrice': 3,
            'episodes': [
              {
                'episodeId': 'favorite_ep_1',
                'episodeNumber': 1,
                'title': 'Favorite Episode 1',
                'pointPrice': 3,
                'ready': true,
                'locked': false,
              },
            ],
          },
        }),
      );
    }
    throw StateError('Unexpected Tenant Edge request: ${request.path}');
  }
}

void main() {
  testWidgets('watch history tile opens an empty history state', (
    tester,
  ) async {
    final flavor = FlavorConfig.hongguo();
    final runtime = AppRuntime(
      flavor: flavor,
      client: TenantAdapterClient(
        baseUri: Uri.parse('https://tenant-edge.example.test'),
        transport: LibraryFakeTransport(),
      ),
    );
    addTearDown(runtime.dispose);

    await tester.pumpWidget(
      AppRuntimeScope(
        runtime: runtime,
        child: MaterialApp(home: AccountScreen(flavor: flavor)),
      ),
    );

    await tester.tap(find.text('Watch History'));
    await tester.pumpAndSettle();

    expect(find.text('No watched episodes yet'), findsOneWidget);
  });

  testWidgets('favorites tile opens an empty favorites state', (
    tester,
  ) async {
    final flavor = FlavorConfig.hongguo();
    final runtime = AppRuntime(
      flavor: flavor,
      client: TenantAdapterClient(
        baseUri: Uri.parse('https://tenant-edge.example.test'),
        transport: LibraryFakeTransport(),
      ),
    );
    addTearDown(runtime.dispose);

    await tester.pumpWidget(
      AppRuntimeScope(
        runtime: runtime,
        child: MaterialApp(home: AccountScreen(flavor: flavor)),
      ),
    );

    await tester.tap(find.text('Favorites'));
    await tester.pumpAndSettle();

    expect(find.text('No favorites yet'), findsOneWidget);
  });

  testWidgets('watch history entry opens its player episode', (
    tester,
  ) async {
    final flavor = FlavorConfig.hongguo();
    final runtime = AppRuntime(
      flavor: flavor,
      client: TenantAdapterClient(
        baseUri: Uri.parse('https://tenant-edge.example.test'),
        transport: LibraryFakeTransport(),
      ),
    );
    addTearDown(runtime.dispose);
    runtime.recordPlayback(
      dramaId: 'drama_history',
      dramaTitle: 'History Runtime Drama',
      episodeId: 'history_ep_2',
      episodeTitle: 'History Episode 2',
    );

    await tester.pumpWidget(
      AppRuntimeScope(
        runtime: runtime,
        child: MaterialApp(home: AccountScreen(flavor: flavor)),
      ),
    );

    await tester.tap(find.text('Watch History'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('History Runtime Drama'));
    await tester.pumpAndSettle();

    expect(find.textContaining('History Runtime Drama'), findsWidgets);
    expect(find.textContaining('History Episode 2'), findsWidgets);
    expect(find.text('Unlock and Play'), findsOneWidget);
  });

  testWidgets('favorite entry opens current drama detail from Tenant Edge', (
    tester,
  ) async {
    final transport = LibraryFakeTransport();
    final flavor = FlavorConfig.hongguo();
    final runtime = AppRuntime(
      flavor: flavor,
      client: TenantAdapterClient(
        baseUri: Uri.parse('https://tenant-edge.example.test'),
        transport: transport,
      ),
    );
    addTearDown(runtime.dispose);
    runtime.toggleFavorite(
      dramaId: 'drama_favorite',
      title: 'Favorite Runtime Drama',
    );

    await tester.pumpWidget(
      AppRuntimeScope(
        runtime: runtime,
        child: MaterialApp(home: AccountScreen(flavor: flavor)),
      ),
    );

    await tester.tap(find.text('Favorites'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Favorite Runtime Drama'));
    await tester.pumpAndSettle();

    expect(find.text('Favorite Runtime Drama'), findsWidgets);
    expect(find.text('Favorite Episode 1'), findsNothing);
    expect(find.text('Start Watching'), findsOneWidget);
    expect(transport.requests.single.path, '/dramas/drama_favorite');
  });
}
