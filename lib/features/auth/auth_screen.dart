import 'dart:async';

import 'package:app_links/app_links.dart';
import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../app/app_runtime.dart';
import '../../core/config/app_capabilities.dart';
import '../../flavor/flavor.dart';
import '../../theme/template_theme.dart';

typedef OAuthUrlLauncher = Future<bool> Function(Uri uri);

abstract class OAuthCallbackLinks {
  Future<Uri?> getInitialLink();

  Stream<Uri> get uriLinkStream;
}

class SystemOAuthCallbackLinks implements OAuthCallbackLinks {
  SystemOAuthCallbackLinks({AppLinks? appLinks})
      : _appLinks = appLinks ?? AppLinks();

  final AppLinks _appLinks;

  @override
  Future<Uri?> getInitialLink() {
    return _appLinks.getInitialLink();
  }

  @override
  Stream<Uri> get uriLinkStream => _appLinks.uriLinkStream;
}

class OAuthCallbackPayload {
  const OAuthCallbackPayload({
    required this.code,
    this.provider,
    this.oauthStartId,
    this.state,
  });

  final String code;
  final String? provider;
  final String? oauthStartId;
  final String? state;
}

class AuthScreen extends StatefulWidget {
  const AuthScreen({
    required this.flavor,
    this.launchOAuthUrl = _launchOAuthUrl,
    this.callbackLinks,
    super.key,
  });

  final FlavorConfig flavor;
  final OAuthUrlLauncher launchOAuthUrl;
  final OAuthCallbackLinks? callbackLinks;

  @override
  State<AuthScreen> createState() => _AuthScreenState();
}

Future<bool> _launchOAuthUrl(Uri uri) {
  return launchUrl(uri, mode: LaunchMode.externalApplication);
}

class _AuthScreenState extends State<AuthScreen> {
  final emailController = TextEditingController(text: 'guest@example.com');
  final emailCodeController = TextEditingController(text: '123456');
  final oauthCodeController = TextEditingController();
  final oauthStateController = TextEditingController();
  late final OAuthCallbackLinks callbackLinks;
  StreamSubscription<Uri>? oauthCallbackSubscription;
  bool oauthCallbackListening = false;
  bool submitting = false;
  String? resultText;
  String? errorText;
  String? emailChallengeId;
  String? oauthProvider;
  String? oauthStartId;

  @override
  void initState() {
    super.initState();
    callbackLinks = widget.callbackLinks ?? SystemOAuthCallbackLinks();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!oauthCallbackListening) {
      oauthCallbackListening = true;
      startOAuthCallbackListening();
    }
  }

  @override
  void dispose() {
    oauthCallbackSubscription?.cancel();
    emailController.dispose();
    emailCodeController.dispose();
    oauthCodeController.dispose();
    oauthStateController.dispose();
    super.dispose();
  }

  void startOAuthCallbackListening() {
    callbackLinks.getInitialLink().then((uri) {
      if (uri != null) {
        handleOAuthCallbackUri(uri);
      }
    }).catchError((Object error) {
      if (mounted) {
        setState(() {
          errorText = '$error';
        });
      }
    });
    try {
      oauthCallbackSubscription = callbackLinks.uriLinkStream.listen(
        handleOAuthCallbackUri,
        onError: (Object error) {
          if (mounted) {
            setState(() {
              errorText = '$error';
            });
          }
        },
      );
    } catch (error) {
      errorText = '$error';
    }
  }

  Future<void> startProvider(AuthProvider provider) async {
    final runtime = AppRuntimeScope.of(context);
    setState(() {
      submitting = true;
      resultText = null;
      errorText = null;
    });
    try {
      _ensureAuthProviderEnabled(runtime, provider.wireValue);
      if (provider == AuthProvider.email) {
        final email = emailController.text.trim();
        if (email.isEmpty) {
          throw ArgumentError('Email is required.');
        }
        final result = await runtime.client.startEmailAuth(
          email: email,
          endUserRef: runtime.endUserRef,
        );
        if (!mounted) {
          return;
        }
        setState(() {
          emailChallengeId = result.challengeId;
          resultText =
              'Email challenge ${result.challengeId} sent to ${result.emailMasked}.';
        });
      } else {
        final result = await runtime.client.startOAuth(
          provider: provider.wireValue,
          endUserRef: runtime.endUserRef,
        );
        final authUri = Uri.tryParse(result.authUrl);
        if (authUri == null || !authUri.hasScheme) {
          throw StateError('Tenant OAuth URL is unavailable.');
        }
        final launched = await widget.launchOAuthUrl(authUri);
        if (!launched) {
          throw StateError('Unable to open tenant OAuth URL.');
        }
        if (!mounted) {
          return;
        }
        setState(() {
          oauthProvider = result.provider;
          oauthStartId = result.oauthStartId;
          resultText =
              '${result.provider} sign-in opened for tenant ${result.tenantId}.';
        });
      }
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        errorText = '$error';
      });
    } finally {
      if (mounted) {
        setState(() {
          submitting = false;
        });
      }
    }
  }

  Future<void> verifyEmailChallenge() async {
    final runtime = AppRuntimeScope.of(context);
    final challengeId = emailChallengeId;
    setState(() {
      submitting = true;
      errorText = null;
    });
    try {
      if (challengeId == null) {
        throw StateError('Start email login first.');
      }
      final code = emailCodeController.text.trim();
      if (code.isEmpty) {
        throw ArgumentError('Verification code is required.');
      }
      final result = await runtime.client.verifyEmailAuth(
        challengeId: challengeId,
        code: code,
        endUserRef: runtime.endUserRef,
      );
      runtime.applyAuthenticatedAccount(result.account);
      if (!mounted) {
        return;
      }
      setState(() {
        resultText = 'Email verified for ${result.account.accountRefMasked}.';
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        errorText = '$error';
      });
    } finally {
      if (mounted) {
        setState(() {
          submitting = false;
        });
      }
    }
  }

  Future<void> completeOAuthSignIn({
    OAuthCallbackPayload? callback,
  }) async {
    final runtime = AppRuntimeScope.of(context);
    final provider = callback?.provider ?? oauthProvider;
    final startId = callback?.oauthStartId ?? oauthStartId;
    setState(() {
      submitting = true;
      errorText = null;
    });
    try {
      if (provider == null || startId == null) {
        throw StateError('Start social login first.');
      }
      _ensureAuthProviderEnabled(runtime, provider);
      final code = callback?.code ?? oauthCodeController.text.trim();
      if (code.isEmpty) {
        throw ArgumentError('OAuth callback code is required.');
      }
      final result = await runtime.client.completeOAuth(
        provider: provider,
        oauthStartId: startId,
        code: code,
        state: callback?.state ?? oauthStateController.text.trim(),
        endUserRef: runtime.endUserRef,
      );
      runtime.applyAuthenticatedAccount(result.account);
      if (!mounted) {
        return;
      }
      setState(() {
        resultText =
            '${result.provider} verified for ${result.account.accountRefMasked}.';
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        errorText = '$error';
      });
    } finally {
      if (mounted) {
        setState(() {
          submitting = false;
        });
      }
    }
  }

  void _ensureAuthProviderEnabled(AppRuntime runtime, String provider) {
    final enabledProviders = runtime.effectiveCapabilities.normalizedAuthProviders
        .map((item) => item.wireValue)
        .toSet();
    if (!enabledProviders.contains(provider)) {
      throw StateError('Auth provider $provider is not enabled for this app.');
    }
  }

  Future<void> handleOAuthCallbackUri(Uri uri) async {
    final payload = parseOAuthCallbackUri(uri);
    if (payload == null || !mounted) {
      return;
    }
    await completeOAuthSignIn(callback: payload);
  }

  OAuthCallbackPayload? parseOAuthCallbackUri(Uri uri) {
    final query = uri.queryParameters;
    final code = query['code']?.trim();
    if (code == null || code.isEmpty) {
      return null;
    }
    final hostMatches = uri.host == 'auth';
    final pathSegments = uri.pathSegments;
    final pathLooksLikeOAuth = pathSegments.contains('oauth') ||
        pathSegments.contains('callback') ||
        pathSegments.contains('auth');
    if (!hostMatches && !pathLooksLikeOAuth && query['oauthStartId'] == null) {
      return null;
    }
    final pathProvider = _providerFromPath(pathSegments);
    return OAuthCallbackPayload(
      code: code,
      provider: query['provider']?.trim().isNotEmpty == true
          ? query['provider']!.trim()
          : pathProvider,
      oauthStartId: query['oauthStartId']?.trim().isNotEmpty == true
          ? query['oauthStartId']!.trim()
          : null,
      state: query['state']?.trim().isNotEmpty == true
          ? query['state']!.trim()
          : null,
    );
  }

  String? _providerFromPath(List<String> pathSegments) {
    final oauthIndex = pathSegments.indexOf('oauth');
    if (oauthIndex >= 0 && oauthIndex + 1 < pathSegments.length) {
      return pathSegments[oauthIndex + 1];
    }
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final runtime = AppRuntimeScope.of(context);
    final capabilities = runtime.effectiveCapabilities;
    final tokens = templateTokensFor(
      capabilities.styleTemplate,
      runtime.effectiveBrandPrimaryColor,
    );
    return Scaffold(
      appBar: AppBar(title: const Text('Login / Register')),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          Icon(Icons.play_circle_fill_rounded, size: 64, color: tokens.primary),
          const SizedBox(height: 14),
          Text(
            'Continue watching on ${runtime.appName}',
            style: Theme.of(
              context,
            ).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w900),
          ),
          const SizedBox(height: 8),
          const Text(
            'Auth providers are configured by the tenant backend. Provider secrets stay on Tenant Edge.',
          ),
          const SizedBox(height: 18),
          if (capabilities.normalizedAuthProviders.contains(
            AuthProvider.email,
          )) ...[
            TextField(
              controller: emailController,
              keyboardType: TextInputType.emailAddress,
              decoration: const InputDecoration(
                labelText: 'Email',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 10),
            if (emailChallengeId != null) ...[
              TextField(
                key: const ValueKey('email-verification-code-input'),
                controller: emailCodeController,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(
                  labelText: 'Email verification code',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 10),
              FilledButton.icon(
                onPressed: submitting ? null : verifyEmailChallenge,
                icon: const Icon(Icons.verified_outlined),
                label: const Text('Verify email'),
              ),
              const SizedBox(height: 10),
            ],
          ],
          if (oauthStartId != null) ...[
            TextField(
              key: const ValueKey('oauth-callback-code-input'),
              controller: oauthCodeController,
              decoration: const InputDecoration(
                labelText: 'OAuth callback code',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 10),
            TextField(
              key: const ValueKey('oauth-callback-state-input'),
              controller: oauthStateController,
              decoration: const InputDecoration(
                labelText: 'OAuth callback state',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 10),
            FilledButton.icon(
              onPressed: submitting ? null : completeOAuthSignIn,
              icon: const Icon(Icons.verified_user_outlined),
              label: Text('Complete ${oauthProvider ?? 'social'} sign-in'),
            ),
            const SizedBox(height: 10),
          ],
          if (resultText != null) ...[
            Text(
              resultText!,
              style: TextStyle(
                color: tokens.primary,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 10),
          ],
          if (errorText != null) ...[
            Text(
              errorText!,
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
            const SizedBox(height: 10),
          ],
          for (final provider in capabilities.normalizedAuthProviders)
            Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: OutlinedButton.icon(
                onPressed: submitting ? null : () => startProvider(provider),
                icon: Icon(
                  provider.wireValue == 'apple'
                      ? Icons.apple
                      : Icons.login_outlined,
                ),
                label: Text('Continue with ${provider.wireValue}'),
              ),
            ),
          const SizedBox(height: 10),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Continue as guest'),
          ),
        ],
      ),
    );
  }
}
